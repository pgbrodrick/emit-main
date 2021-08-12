try:
    import cPickle as pickle
except ImportError:
    import pickle

import os
import shutil
import sys

from emit_main.workflow.workflow_manager import WorkflowManager


def _do_work_on_compute_node(work_dir):

    # Open up the pickle file with the work to be done
    os.chdir(work_dir)
    # sys.path.insert(0, work_dir)
    # print(f"sys.path: {sys.path}")
    with open("job-instance.pickle", "rb") as f:
        job = pickle.load(f)

    # Set up local tmp dir
    wm = WorkflowManager(config_path=job.config_path)
    job.local_tmp_dir = os.path.join(wm.local_tmp_dir, job.task_instance_id)
    os.makedirs(job.local_tmp_dir)
    print(f"Created local tmp dir: {job.local_tmp_dir}")

    # Do the work contained
    try:
        job.work()
    except RuntimeError as e:
        # Move local tmp folder to "error" subfolder under "scratch"
        print("Encountered error with task:  %s" % job)
        error_task_dir = job.tmp_dir.replace("/tmp/", "/error/")
        error_tmp_dir = error_task_dir + "_tmp"
        print(f"Copying local tmp folder {job.local_tmp_dir} to {error_tmp_dir}")
        shutil.copytree(job.local_tmp_dir, error_tmp_dir)
        raise e
    finally:
        # Delete local tmp folder in all cases except when running on debug partition with DEBUG level
        if job.partition != "debug" or (job.partition == "debug" and job.level != "DEBUG"):
            print(f"Deleting task's local tmp folder: {job.local_tmp_dir}")
            shutil.rmtree(job.local_tmp_dir)


def main(args=sys.argv):
    """Run the work() method from the class instance in the file "job-instance.pickle".
    """
    try:
        # Set up logging.
        # logging.basicConfig(level=logging.WARN)
        work_dir = sys.argv[1]
        assert os.path.exists(work_dir), "First argument to sge_runner.py must be a directory that exists"
        _do_work_on_compute_node(work_dir)
    except Exception as e:
        # Dump encoded data that we will try to fetch using mechanize
        print(e)
        raise


if __name__ == '__main__':
    main()
