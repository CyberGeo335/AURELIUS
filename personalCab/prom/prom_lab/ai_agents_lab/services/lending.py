"""M4/M5 application facade. Transactional persistence lives in repositories."""
from ..repositories.lending_repository import LendingRepository
from ..schemas.lending import DemoOffer
from .identifiers import stable_hash


class LendingService:
    def __init__(self,config,assessment_service=None):
        self.repository=LendingRepository(config,assessment_service)

    def run_assessment(self,envelope,arguments):
        return self.repository.run_assessment(envelope,arguments)

    def submit_application(self,envelope,arguments):
        return self.repository.submit_application(envelope,arguments)

    def get_bank_status(self,envelope,arguments):
        return self.repository.get_bank_status(envelope,arguments)

    def review(self,lender_case_id,**review):
        return self.repository.review(lender_case_id,**review)

    def accept_offer(self,envelope,arguments):
        return self.repository.accept_offer(envelope,arguments)

    def execute_demo(self,envelope,arguments):
        return self.repository.execute_demo(envelope,arguments)

    def record_demo_payment(self,case,actor,operation_id,amount):
        return self.repository.record_demo_payment(case,actor,operation_id,amount)
