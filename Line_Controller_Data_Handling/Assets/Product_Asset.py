from .Base_Asset import Asset


class ProductAsset(Asset):
    def __init__(self, shell_id, id_short):
        super().__init__(shell_id, id_short)

        self.bill_of_processes = None
        self.bill_of_materials = None
        self.properties = None