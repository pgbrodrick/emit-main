"""
This code contains the FramesMonitor class that watches depacketized frames to decide when it is time to run image
reassembly

Author: Winston Olson-Duvall, winston.olson-duvall@jpl.nasa.gov
"""

import datetime
import glob
import logging
import os

from emit_main.workflow.l1a_tasks import L1AReassembleRaw, L1AFrameReport
from emit_main.workflow.workflow_manager import WorkflowManager

logger = logging.getLogger("emit-main")


class FramesMonitor:

    def __init__(self, config_path, level="INFO", partition="emit", ignore_missing_frames=False, acq_chunksize=1280,
                 test_mode=False):
        """
        :param config_path: Path to config file containing environment settings
        """

        self.config_path = os.path.abspath(config_path)
        self.level = level
        self.partition = partition
        self.ignore_missing_frames = ignore_missing_frames
        self.acq_chunksize = acq_chunksize
        self.test_mode = test_mode

        # Get workflow manager
        self.wm = WorkflowManager(config_path=config_path)

    def get_recent_reassembly_tasks(self):
        dm = self.wm.database_manager
        stop_time = datetime.datetime.now(tz=datetime.timezone.utc)
        start_time = stop_time - datetime.timedelta(days=1)
        data_collections = dm.find_data_collections_for_reassembly(start=start_time, stop=stop_time)

        tasks = []
        for dc in data_collections:
            logger.info(f"Creating L1AFrameReport task for dcid {dc['dcid']}")
            tasks.append(L1AFrameReport(config_path=self.config_path,
                                        dcid=dc["dcid"],
                                        level=self.level,
                                        partition=self.partition,
                                        ignore_missing_frames=self.ignore_missing_frames,
                                        acq_chunksize=self.acq_chunksize,
                                        test_mode=self.test_mode))

        return tasks