class Scheduler:
    """
    This Class should look at a the output from the CapabilityMatcher, and decide what station a process should be assigned to, and maybe update it in the process_checklist.  
    """
    def __init__(self, checklist):
        self.checklist = checklist

    def get_ready_steps(self):
        return self.checklist.get_ready_steps()