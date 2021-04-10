import os
import threading
from collections import OrderedDict
from copy import deepcopy

import cv2
import numpy as np
import PyQt5.QtCore as QtCore
import PyQt5.QtGui as QtGui
import PyQt5.QtWidgets as QtWidgets
import snooker_ball_tracker.settings as s
from snooker_ball_tracker.ball_tracker import (BallTracker, Logger, Settings,
                                               VideoPlayer)
from snooker_ball_tracker.video_file_stream import VideoFileStream
from snooker_ball_tracker.video_processor import VideoProcessor

from .logging_view import LoggingView
from .settings_view import SettingsView
from .video_player_view import VideoPlayerView


class MainView(QtWidgets.QMainWindow):
    def __init__(self, args):
        super().__init__()

        self.settings_file = args.settings_file

        if self.settings_file:
            s.load(self.settings_file)

        self.setWindowTitle("Snooker Ball Tracker Demo")

        self.central_widget = QtWidgets.QWidget(self)
        self.central_widget_layout = QtWidgets.QGridLayout(self.central_widget)
        self.central_widget_layout.setContentsMargins(30, 30, 30, 30)
        self.central_widget_layout.setSpacing(30)

        self.video_processor_lock = threading.Lock()
        self.video_processor_stop_event = threading.Event()
        self.video_processor = None
        self.video_file_stream = None
        self.video_file = None

        self.logger = Logger()
        self.settings = Settings()
        self.ball_tracker = BallTracker(logger=self.logger, settings=self.settings)

        self.settings_view = SettingsView(self.settings)
        self.logging_view = LoggingView(self.logger)

        self.video_player = VideoPlayer()
        self.video_player.restartChanged.connect(self.restart_video_processor)
        self.video_player_view = VideoPlayerView(self.video_player)

        self.central_widget_layout.addWidget(self.settings_view, 0, 0, 1, 1)
        self.central_widget_layout.addWidget(self.logging_view, 1, 0, 1, 1)
        self.central_widget_layout.addWidget(self.video_player_view, 0, 1, 2, 1)
        self.central_widget_layout.setColumnStretch(1, 2)

        self.setCentralWidget(self.central_widget)

        menu = self.menuBar().addMenu("File")
        action = menu.addAction("Select Video File")
        action.triggered.connect(self.select_file_onclick)

        menu = self.menuBar().addMenu("Settings")
        action = menu.addAction("Load")
        action.triggered.connect(self.load_settings)
        action = menu.addAction("Save")
        action.triggered.connect(self.save_settings)

        action = self.menuBar().addAction("Exit")

        self.menuBar().setNativeMenuBar(False)

    def closeEvent(self, event):
        if self.video_file_stream is not None:
            with self.video_processor_lock:
                self.video_file_stream.stop()
        event.accept()

    def select_file_onclick(self):
        self.video_file, _ = QtWidgets.QFileDialog().getOpenFileName(self, "Select Video File", "")

        if not self.video_file:
            return

        if self.video_processor is not None:
            self.video_processor_stop_event.set()

        try:
            self.video_file_stream = cv2.VideoCapture(self.video_file)
            if not self.video_file_stream.isOpened():
                raise TypeError
        except:
            error = QtWidgets.QMessageBox(self)
            error.setWindowTitle("Invalid Video File!")
            error.setText('Invalid file, please select a video file!')
            error.exec_()
            return

        self.start_video_processor()

    def start_video_processor(self):
        self.video_file_stream = VideoFileStream(
            self.video_file, video_player=self.video_player,
            colour_settings=self.settings.models["colour_detection"].colours, queue_size=1)

        self.video_processor_stop_event = threading.Event()
        self.video_processor = VideoProcessor(
            video_stream=self.video_file_stream, 
            logger=self.logger, video_player=self.video_player, 
            colour_settings=self.settings.models["colour_detection"],
            ball_tracker=self.ball_tracker, lock=self.video_processor_lock, 
            stop_event=self.video_processor_stop_event)
        self.video_processor.start()

    def restart_video_processor(self, restart):
        if restart:
            if self.video_processor is not None:
                self.video_processor_stop_event.set()
            self.start_video_processor()

    def load_settings(self):
        settings_file, _ = QtWidgets.QFileDialog().getOpenFileName(self, "Load Settings", "")
        if not settings_file:
            return

        self.settings_file = settings_file
        threading.Thread(target=self.__load_settings, args=(settings_file,), daemon=True).start()

    def __load_settings(self, settings_file):
        success, error = s.load(settings_file)
        if success:
            self.settings.models["colour_detection"].colours = deepcopy(s.COLOURS)
            self.settings.models["ball_detection"].blob_detector = deepcopy(s.BLOB_DETECTOR)

    def save_settings(self):
        data = [("Json Files", ".json")]
        name, ext = os.path.splitext(os.path.basename(self.settings_file))
        settings_file, _ = QtWidgets.QFileDialog().getSaveFileName(self, "Save Settings", self.settings_file)

        if not settings_file:
            return

        self.settings_file = settings_file
        threading.Thread(target=self.__save_settings, args=(settings_file,), daemon=True).start()

    def __save_settings(self, settings_file):
        s.COLOURS = self.settings.models["colour_detection"].colours
        s.BLOB_DETECTOR = self.settings.models["ball_detection"].blob_detector
        success, error = s.save(settings_file)
