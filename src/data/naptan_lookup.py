import pandas as pd

class NaPTANLookup:
    def __init__(self, file_path: str = "../data/Stops.csv"):
        df = pd.read_csv(file_path)

        self.naptan_to_name = dict(zip(df["NaptanCode"], df["CommonName"]))
        self.name_to_naptan = dict(zip(df["CommonName"], df["NaptanCode"]))

    def get_stop_name(self, stop_id: str) -> str:
        return self.naptan_to_name.get(stop_id, "Unknown Stop ID")

    def get_stop_id(self, stop_name: str) -> str:
        return self.name_to_naptan.get(stop_name, "Unknown Stop Name")