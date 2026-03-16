

class ResourceManager:
    def __init__(self, Resources):
        self.resource_nodes = Resources

    


#This should contain a class that we can construct with all the resources we have.
#This it should have a function that:
# allows us to insert a requried skill and component and recieve a list of resoruces that have that skill and is compatible with that component
# allows us to insert a component and returns a list of resources that have the specific component in their internal storage
# allows us to insert two different resources and return a list, showing if and how they are connected through connection points
# Lastly, it should be able to generate a command that can later be sent over MQTT