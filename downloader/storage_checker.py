import os
from datetime import datetime

from .config import mediaDir, MAXIMUM_FILES_COUNT


class StorageFilter():


    def get_files_in_dir(self, directory):
        return [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and not f.startswith(".")]


    def filter_storage(self):
        if _DEBUG_:
            print("filter_storage started")
        files_dir = os.path.join(os.getcwd(), mediaDir)
        files = self.get_files_in_dir(files_dir)
        files.sort(key=lambda x: -os.path.getmtime(x))
        print(files)
        if len(files) <= MAXIMUM_FILES_COUNT:
            if _DEBUG_:
                print("filter_storage files < MAXIMUM_FILES_COUNT")
            return
        files_to_delete = files[MAXIMUM_FILES_COUNT:]
        for file in files_to_delete:
            os.unlink(file)
