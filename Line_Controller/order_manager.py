class ProductionOrder:
    def __init__(self, order_id, product, quantity, planned_start):
        self.order_id = order_id
        self.product = product
        self.quantity = quantity
        self.planned_start = planned_start

def generate_products(order):
    products = []

    if not products:
        print("No products found. Cannot create test order.")

    
    for i in range(order.quantity):
        product_instance = {
            "id": f"{order.product}_{i+1}",
            "product_type": order.product,
            "current_process":0
        }

        products.append(product_instance)

    return products