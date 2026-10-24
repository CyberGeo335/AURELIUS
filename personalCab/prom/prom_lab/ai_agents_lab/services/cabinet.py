"""Trusted DEMO controls over scoped, transactional repositories."""
from ..repositories.cabinet_repository import CabinetRepository


class CabinetControls:
    def __init__(self,repository,allowed_company_ids):
        self.repository=CabinetRepository(repository,allowed_company_ids)

    def execute(self,actor,session,request_id,kind,arguments):
        return self.repository.execute(actor,session,request_id,kind,arguments)

    def applications(self,actor):
        return self.repository.applications(actor)

    def lender_status(self,case,actor):
        return self.repository.lender_status(case,actor)

    def documents(self,case,actor):
        return self.repository.documents(case,actor)

    def upload(self,case,actor,filename,encoded):
        return self.repository.upload(case,actor,filename,encoded)
