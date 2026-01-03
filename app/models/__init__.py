from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.message import Message
from app.models.user import User
from app.models.technician import Technician
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.quote import Quote
from app.models.sms_consent import SMSConsent, SMSConsentAudit
from app.models.activity import Activity
from app.models.ticket import Ticket
from app.models.equipment import Equipment
from app.models.inventory import InventoryItem

# Phase 1: AI Infrastructure
from app.models.ai_embedding import AIEmbedding, AIConversation, AIMessage

# Phase 2: RingCentral / Call Center
from app.models.call_log import CallLog
from app.models.call_disposition import CallDisposition

# Phase 3: E-Signatures
from app.models.signature import SignatureRequest, Signature, SignedDocument

# Phase 4: Pricing Engine
from app.models.pricing import ServiceCatalog, PricingZone, PricingRule, CustomerPricingTier

# Phase 5: AI Agents
from app.models.ai_agent import AIAgent, AgentConversation, AgentMessage, AgentTask

# Phase 6: Predictive Analytics
from app.models.prediction import LeadScore, ChurnPrediction, RevenueForecast, DealHealth, PredictionModel

# Phase 7: Marketing Automation
from app.models.marketing import MarketingCampaign, MarketingWorkflow, WorkflowEnrollment, EmailTemplate, SMSTemplate

# Phase 10: Payroll
from app.models.payroll import PayrollPeriod, TimeEntry, Commission, TechnicianPayRate

__all__ = [
    # Core models
    "Customer",
    "WorkOrder",
    "Message",
    "User",
    "Technician",
    "Invoice",
    "Payment",
    "Quote",
    "SMSConsent",
    "SMSConsentAudit",
    "Activity",
    "Ticket",
    "Equipment",
    "InventoryItem",
    # Phase 1: AI
    "AIEmbedding",
    "AIConversation",
    "AIMessage",
    # Phase 2: RingCentral / Call Center
    "CallLog",
    "CallDisposition",
    # Phase 3: E-Signatures
    "SignatureRequest",
    "Signature",
    "SignedDocument",
    # Phase 4: Pricing
    "ServiceCatalog",
    "PricingZone",
    "PricingRule",
    "CustomerPricingTier",
    # Phase 5: AI Agents
    "AIAgent",
    "AgentConversation",
    "AgentMessage",
    "AgentTask",
    # Phase 6: Predictions
    "LeadScore",
    "ChurnPrediction",
    "RevenueForecast",
    "DealHealth",
    "PredictionModel",
    # Phase 7: Marketing
    "MarketingCampaign",
    "MarketingWorkflow",
    "WorkflowEnrollment",
    "EmailTemplate",
    "SMSTemplate",
    # Phase 10: Payroll
    "PayrollPeriod",
    "TimeEntry",
    "Commission",
    "TechnicianPayRate",
]
