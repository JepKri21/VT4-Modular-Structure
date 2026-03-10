class ProcessPlanner:
    def __init__(self, stations):
        """
        stations = {
            station_id : { skill_name : skill_data }
        }
        """
        self.stations = stations
    
    def generate_process_plan(self, product):

        operations = []

        for station_id, skills in self.stations.items():

            for agent, agent_data in skills.items():

                if not isinstance(agent_data, dict):
                    continue

                for operation_name, operation_data in agent_data.items():

                    duration = operation_data.get("Estimated_Duration", 1)

                    operations.append({
                        "operation": operation_name,
                        "duration": float(duration),
                        "station": station_id,
                        "parameters": operation_data.get("Parameters", {})
                    })

        return operations

