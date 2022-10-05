"""
This code contains tasks pertaining DAAC delivery

Author: Winston Olson-Duvall, winston.olson-duvall@jpl.nasa.gov
"""

import datetime
import glob
import json
import logging
import luigi
import os

from emit_main.workflow.output_targets import DAACSceneNumbersTarget
from emit_main.workflow.slurm import SlurmJobTask
from emit_main.workflow.workflow_manager import WorkflowManager
from emit_utils.file_checks import get_gring_boundary_points, get_band_mean

logger = logging.getLogger("emit-main")


class AssignDAACSceneNumbers(SlurmJobTask):
    """
    Assigns DAAC scene numbers to all scenes in the orbit
    """

    config_path = luigi.Parameter()
    orbit_id = luigi.Parameter()
    level = luigi.Parameter()
    partition = luigi.Parameter()
    override_output = luigi.BoolParameter(default=False)

    memory = 18000

    task_namespace = "emit"

    def requires(self):

        logger.debug(f"{self.task_family} requires: {self.orbit_id}")
        return None

    def output(self):

        logger.debug(f"{self.task_family} output: {self.orbit_id}")

        if self.override_output:
            return None

        wm = WorkflowManager(config_path=self.config_path, orbit_id=self.orbit_id)
        orbit = wm.orbit
        dm = wm.database_manager

        # Get acquisitions in orbit
        acquisitions = dm.find_acquisitions_by_orbit_id(orbit.orbit_id, "science", min_valid_lines=0)
        acquisitions += dm.find_acquisitions_by_orbit_id(orbit.orbit_id, "dark", min_valid_lines=0)
        return DAACSceneNumbersTarget(acquisitions)

    def work(self):

        logger.debug(f"{self.task_family} work: {self.acquisition_id}")

        wm = WorkflowManager(config_path=self.config_path, orbit_id=self.orbit_id)
        orbit = wm.orbit
        pge = wm.pges["emit-main"]
        dm = wm.database_manager

        # Get acquisitions in orbit
        acquisitions = dm.find_acquisitions_by_orbit_id(orbit.orbit_id, "science", min_valid_lines=0)
        acquisitions += dm.find_acquisitions_by_orbit_id(orbit.orbit_id, "dark", min_valid_lines=0)

        # Throw error if some acquisitions have daac scene numbers but others don't
        count = 0
        acq_ids = []
        for acq in acquisitions:
            if "daac_scene" in acq:
                count += 1
            acq_ids.append(acq["acquisition_id"])

        if not self.override_output and 0 < count < len(acquisitions):
            raise RuntimeError(f"While assigning scene numbers for DAAC, found some with scene numbers already. "
                               f"Aborting...")

        # Assign the scene numbers
        acq_ids = list(set(acq_ids))
        acq_ids.sort()
        daac_scene = 1
        for acq_id in acq_ids:
            dm.update_acquisition_metadata(acq_id, {"daac_scene": str(daac_scene).zfill(3)})

            log_entry = {
                "task": self.task_family,
                "pge_name": pge.repo_url,
                "pge_version": pge.version_tag,
                "pge_input_files": {
                    "orbit_id": orbit.orbit_id
                },
                "pge_run_command": "N/A - DB updates only",
                "documentation_version": "N/A",
                "log_timestamp": datetime.datetime.now(tz=datetime.timezone.utc),
                "completion_status": "SUCCESS",
                "output": {
                    "daac_scene_number": str(daac_scene).zfill(3)
                }
            }

            dm.insert_acquisition_log_entry(acq_id, log_entry)

            # Increment scene number
            daac_scene += 1

        # Update orbit processing log too
        log_entry = {
            "task": self.task_family,
            "pge_name": pge.repo_url,
            "pge_version": pge.version_tag,
            "pge_input_files": {
                "orbit_id": orbit.orbit_id
            },
            "pge_run_command": "N/A - DB updates only",
            "documentation_version": "N/A",
            "log_timestamp": datetime.datetime.now(tz=datetime.timezone.utc),
            "completion_status": "SUCCESS",
            "output": {
                "number_of_scenes": daac_scene - 1
            }
        }

        dm.insert_orbit_log_entry(self.orbit_id, log_entry)


class GetAdditionalMetadata(SlurmJobTask):
    """
    Looks up additional attributes (like gring, solar zenith, etc) and saves to DB for easy access
    """

    config_path = luigi.Parameter()
    acquisition_id = luigi.Parameter()
    level = luigi.Parameter()
    partition = luigi.Parameter()

    memory = 18000

    task_namespace = "emit"

    def requires(self):

        logger.debug(f"{self.task_family} requires: {self.acquisition_id}")
        return None

    def output(self):

        logger.debug(f"{self.task_family} output: {self.acquisition_id}")
        return None

    def work(self):

        logger.debug(f"{self.task_family} work: {self.acquisition_id}")

        wm = WorkflowManager(config_path=self.config_path, acquisition_id=self.acquisition_id)
        acq = wm.acquisition
        pge = wm.pges["emit-main"]
        dm = wm.database_manager

        # Get additional attributes and add to DB
        glt_gring = get_gring_boundary_points(acq.glt_hdr_path)
        mean_solar_azimuth = get_band_mean(acq.obs_img_path, 1)
        mean_solar_zenith = get_band_mean(acq.obs_img_path, 2)
        meta = {
            "gring": glt_gring,
            "mean_solar_azimuth": mean_solar_azimuth,
            "mean_solar_zenith": mean_solar_zenith
        }
        dm.update_acquisition_metadata(acq.acquisition_id, meta)

        log_entry = {
            "task": self.task_family,
            "pge_name": pge.repo_url,
            "pge_version": pge.version_tag,
            "pge_input_files": {
                "l1b_glt_hdr_path": acq.glt_hdr_path,
                "l1b_obs_img_path": acq.obs_img_path
            },
            "pge_run_command": "N/A - DB updates only",
            "documentation_version": "N/A",
            "log_timestamp": datetime.datetime.now(tz=datetime.timezone.utc),
            "completion_status": "SUCCESS",
            "output": meta
        }

        dm.insert_acquisition_log_entry(self.acquisition_id, log_entry)
