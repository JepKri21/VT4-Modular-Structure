class Product:
    def __init__(self, product_id, bop, bom):
        self.product_id = product_id
        self.bop = bop
        self.bom = bom

def extract_product_data(parsed_submodels):
    bop = parsed_submodels.get("BoP", None)
    bom = parsed_submodels.get("BoM", None)
    return bop, bom