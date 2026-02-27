from .Base_Asset import Asset


class ResourceAsset(Asset):
    def __init__(self, shell_id, id_short):
        super().__init__(shell_id, id_short)

        #Here we add the different data classes/submodels that we need
        self.communication = None
        self.skills = None
        self.location = None
        self.item_capacity = None

    def is_resource(self):
        return True