class Asset:
    def __init__(self, shell_id: str, id_short: str):
        self.shell_id = shell_id
        self.id_short = id_short

    def is_resource(self):
        return False