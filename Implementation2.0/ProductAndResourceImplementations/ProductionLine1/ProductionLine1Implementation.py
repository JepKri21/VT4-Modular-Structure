#This should first create the shell and submodels from the yaml files and publish them to the server.

#It should also contain the PackML implementation, aka, this should be the main script for this resource
#Technically this isn't a resource, but it would still make sense that a production line has a PackML implementation
#This could also be the way to communicate line-relevant things, and potentially store orders or something
#This should NOT be the line-controller implementation. 
#Or, I mean, maybe it could be, where using START would just result in it running the control loop until every order is finished
#Orders could just be messages, OR they could be submodels published to the shell 
#However, I'm not sure how that would work, if you have to update the shell every time a new order is given? As I don't think you can just "add" a submodel