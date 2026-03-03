class DigitalFactory:
    def __init__(self):
        self.resources = []
        self.products = []

    def find_capable_resources(self, process_step):
        capable = []

        for resource in self.resources:
            if not resource.skills:
                continue

            for skill in resource.skills.skills:
                if skill.supports_process(process_step):
                    capable.append(resource)

        return capable