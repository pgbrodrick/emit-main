import datetime
import logging
import os
import pickle
import shutil
import subprocess
import sys
import time

import luigi

from file_manager import FileManager

FORMAT = "format=%(levelname)s [%(module)s]: %(message)s"
logging.basicConfig(level=logging.DEBUG, format=FORMAT)

logger = logging.getLogger("emit-workflow")

def _build_sbatch_script(tmp_dir, cmd, job_name, outfile, errfile, conda_env):
    """Create shell script to submit to Slurm queue via `sbatch`

    Returns path to sbatch script

    """

    conda_init_script="/shared/anaconda3/etc/profile.d/conda.sh"

    sbatch_template = """#!/bin/bash
#SBATCH -J {job_name}
#SBATCH --output={outfile}
#SBATCH --error={errfile}
#SBATCH -n1
#SBATCH --ntasks-per-node=1
source {conda_init_script}
conda activate {conda_env}
{cmd}
    """
    sbatch_script = os.path.join(tmp_dir, job_name+".sh")
    with open(sbatch_script, "w") as f:
        f.write(
            sbatch_template.format(
                cmd=cmd,
                job_name=job_name, 
                outfile=outfile, 
                errfile=errfile,
                conda_init_script=conda_init_script,
                conda_env=conda_env)
            )
    return sbatch_script

def _parse_squeue_state(squeue_out, job_id):
    """Parse "state" column from squeue output for given job_id

    Returns state for the *first* job matching job_id. Returns 'u' if
    `squeue` output is empty or job_id is not found.

    """

    invalid_job_str = "Invalid job id specified"
    if invalid_job_str in squeue_out:
        return "u"

    lines = squeue_out.split('\n')

    for line in lines:
        if "JOBID" in line:
            continue
        elif len(line.strip()) == 0:
            continue
        else:
            returned_id = line.split()[0]
            state = line.split()[4]
            logging.debug("Squeue for job %i returned ID: %s, State: %s" % (job_id, returned_id, state))
            return state

    return "u"

def _get_sbatch_errors(errfile):
    """Checks error file for errors and returns result

    Returns contents of error file.  Returns empty string if empty.

    """
    errors = ""
    if not os.path.exists(errfile):
        logging.info("No error file found at %s" % errfile)
    with open(errfile, "r") as f:
        errors = f.read()
    return errors

class SlurmJobTask(luigi.Task):

    config_path = luigi.Parameter()

    # TODO: Make this dynamic
    conda_env = "/shared/anaconda3/envs/isat-dev"

    def _dump(self, out_dir=''):
        """Dump instance to file."""
        with self.no_unpicklable_properties():
            self.job_file = os.path.join(out_dir, 'job-instance.pickle')
            logging.debug("Pickling to file: %s" % self.job_file)
            pickle.dump(self, open(self.job_file, "wb"), protocol=2)

    def _init_local(self):

        # Create tmp folder
        #base_tmp_dir = self.shared_tmp_dir
        base_tmp_dir = "/beegfs/scratch/tmp/"
        timestamp = datetime.datetime.now().strftime("%Y%m%dt%H%M%S")
#        timestamp = datetime.datetime.now().strftime('%Y%m%dt%H%M%S_%f') # Use this for microseconds
        folder_name = self.acquisition_id + "_" + self.task_family + "_v" + timestamp

        for b,a in [(' ',''),('(','_'),(')','_'),(',','_'),('/','_')]:
          folder_name = folder_name.replace(b,a)
        self.tmp_dir = os.path.join(base_tmp_dir, folder_name)
        max_filename_length = os.fstatvfs(0).f_namemax
        self.tmp_dir = self.tmp_dir[:max_filename_length]
        logging.info("Created tmp dir: %s", self.tmp_dir)
        os.makedirs(self.tmp_dir)

        # Copy config file to tmp dir
        shutil.copy(self.config_path, self.tmp_dir)

        # Dump the code to be run into a pickle file
        logging.debug("Dumping pickled class")
        self._dump(self.tmp_dir)

    def _run_job(self):

        # Build an sbatch script  that will run slurm_runner.py on the directory we've specified
        runner_path = os.path.join(os.path.abspath(os.getcwd()), "slurm_runner.py")
        # enclose tmp_dir in quotes to protect from special escape chars
        job_str = 'python {0} "{1}"'.format(runner_path, self.tmp_dir)

        # Build sbatch script
        self.outfile = os.path.join(self.tmp_dir, 'job.out')
        self.errfile = os.path.join(self.tmp_dir, 'job.err')
        #TODO: Get conda_env from config or create parameter? May need to change with environment.
        logging.debug("### self.conda_env is %s" % self.conda_env)
        sbatch_script = _build_sbatch_script(self.tmp_dir, job_str, self.task_family, self.outfile,
                                         self.errfile, self.conda_env)
        logging.debug('sbatch script: ' + sbatch_script)

        # Submit the job and grab job ID
        output = subprocess.check_output("sbatch " + sbatch_script, shell=True)
        self.job_id = int(output.decode("utf-8").split(" ")[-1])
        logging.info("%s %s submitted with job id %i" % (self.acquisition_id, self.task_family, self.job_id))

        self._track_job()

        # Now delete the temporaries, if they're there.
       #if self.tmp_dir and os.path.exists(self.tmp_dir):
       #    logger.info('Removing temporary directory %s' % self.tmp_dir)
       #    shutil.rmtree(self.tmp_dir)

    def _track_job(self):
        while True:
            # Sleep for a little bit
#            time.sleep(random.randint(POLL_TIME_RANGE[0], POLL_TIME_RANGE[1]))
            time.sleep(30)

            # See what the job's up to
            logging.info("Checking status of job %i..." % self.job_id)
            squeue_out = subprocess.check_output(["squeue", "-j", str(self.job_id)]).decode("utf-8")
            logging.debug("squeue_out is\n %s" % squeue_out)
            slurm_status = _parse_squeue_state(squeue_out, self.job_id)
            if slurm_status == "PD":
                logging.info("%s %s with job id %i is PENDING..." % (self.acquisition_id, self.task_family, self.job_id))
            if slurm_status == "R":
                logging.info("%s %s with job id %i is RUNNING..." % (self.acquisition_id, self.task_family, self.job_id))
            if slurm_status == "S":
                logging.info("%s %s with job id %i is SUSPENDED..." % (self.acquisition_id, self.task_family, self.job_id))
            if slurm_status == "u":
                errors = _get_sbatch_errors(self.errfile)
                # If no errors, then must be finished
                if not errors:
                    logging.info("%s %s with job id %i has COMPLETED WITH NO ERRORS " % (self.acquisition_id, self.task_family, self.job_id))
                else: # then we have completed with errors
                    logging.info("%s %s with job id %i has COMPLETED WITH ERRORS/WARNINGS:\n%s" % (self.acquisition_id, self.task_family, self.job_id, errors))
                break
            #TODO: Add the rest of the states from https://slurm.schedmd.com/squeue.html

    def run(self):

        fm = FileManager(config_path=self.config_path)

        if fm.luigi_local_scheduler:
            # Run job locally without Slurm scheduler
            logger.debug("Running task locally: %s" % self.task_family)
            self.work()
        else:
            # Run the job
            logger.debug("Running task with Slurm: %s" % self.task_family)
            self._init_local()
            self._run_job()

    def work(self):
        """Override this method, rather than ``run()``,  for your actual work."""
        pass
