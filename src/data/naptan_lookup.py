import pandas as pd
from logging import getLogger

class NaPTANLookup:
    def __init__(self, file_path: str = "../data/NLC_Naptan.csv"):
        df = pd.read_csv(file_path)

        self.naptan_to_name = dict(zip(df["PrimaryNaptanStopArea"], df["UniqueStationName"]))
        self.name_to_naptan = dict(zip(df["UniqueStationName"], df["PrimaryNaptanStopArea"]))

        self._logger = getLogger(__name__)
        self._logger.info(f"Loaded NaPTAN lookup with {len(self.naptan_to_name)} entries")

    def get_stop_name(self, stop_id: str) -> str:
        mapping = self.naptan_to_name.get(stop_id, "Unknown Stop ID")

        if mapping == "Unknown Stop ID":
            self._logger.warning(f"NaPTAN lookup failed for stop ID: {stop_id}")

        return mapping

    def get_stop_id(self, stop_name: str) -> str:
        return self.name_to_naptan.get(stop_name, "Unknown Stop Name")