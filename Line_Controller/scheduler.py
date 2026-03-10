class Scheduler:

    def __init__(self, resource_manager):

        self.rm = resource_manager


    def schedule_product(self, product, operations):

        time = 0
        schedule = []

        for op in operations:

            station = op["station"]
            duration = op["duration"]

            start_time = max(time, self.rm.get_next_available_time(station))

            end_time = self.rm.reserve(
                station,
                product["id"],
                start_time,
                duration
            )

            schedule.append({
                "product": product["id"],
                "operation": op["operation"],
                "station": station,
                "start": start_time,
                "end": end_time
            })

            time = end_time

        return schedule