class ResourceManager:
    def __init__(self, stations):
        self.resources = {}

        for station_id in stations:
            self.resources[station_id] = {
                "busy_until": 0,
                "current_product": None
            }

    def is_available(self, station_id, time):

        return time >= self.resources[station_id]["busy_until"]
    
    def reserve(self, station_id, product_id, start_time, duration):

        end_time = start_time + duration

        self.resources[station_id]["busy_until"] = end_time
        self.resources[station_id]["current_product"] = product_id

        return end_time
    
    def get_next_available_time(self, station_id):

        return self.resources[station_id]["busy_until"]