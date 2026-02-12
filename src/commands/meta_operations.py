from data.tfl_client import TflClient


class MetaOperationsCommand:
    def __init__(self):
        self.tfl_client = TflClient()

    def get_disruption_categories(self) -> list[str]:
        return self.tfl_client.get_valid_disruption_categories()

    def get_modes(self):
        return self.tfl_client.get_valid_modes()

    def get_all_stops(self):
        return self.tfl_client.get_stop_points_by_mode()
