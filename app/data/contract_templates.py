"""
MAC Septic Services — Production-Ready Contract Templates

Based on:
- Texas TCEQ 30 TAC Chapter 285 (On-Site Sewage Facilities)
- Texas Health & Safety Code Chapter 366
- Hays County / Central Texas county OSSF requirements
- Texas Business & Commerce Code (auto-renewal disclosure)

All contracts are designed to:
1. Maximize customer retention through value + switching costs
2. Protect MAC Septic with strong legal clauses
3. Comply with Texas state and county regulations
"""

# ============================================================
# SHARED LEGAL CLAUSES (inserted into every contract)
# ============================================================

SHARED_DEFINITIONS = """
## DEFINITIONS

- **"Company"** means MAC Septic Services, LLC, a Texas limited liability company, its successors and assigns.
- **"Customer"** means the property owner or authorized representative identified above.
- **"System"** or **"OSSF"** means the on-site sewage facility, including all tanks, lines, distribution systems, aerobic treatment units, spray heads, pumps, alarms, and related components located at the Service Address.
- **"Service Address"** means the property address where the System is located, as identified above.
- **"Maintenance Visit"** means a scheduled visit by a Company technician to inspect, service, and maintain the System in accordance with TCEQ regulations and the scope of this Agreement.
- **"Emergency Service"** means any service requested outside of scheduled Maintenance Visits or performed on an urgent basis.
- **"TCEQ"** means the Texas Commission on Environmental Quality.
- **"Permitting Authority"** means Hays County or the applicable county/municipality with OSSF jurisdiction.
"""

SHARED_PAYMENT_TERMS = """
## PAYMENT TERMS

**A. Payment Due.** All fees are due upon receipt of invoice unless otherwise specified. The Company accepts payment by credit card, ACH/bank transfer, check, or cash. The Customer authorizes the Company to charge the payment method on file for all amounts due under this Agreement.

**B. Late Payment.** Any payment not received within thirty (30) days of the invoice date shall incur a late fee of $25.00 or 1.5% of the outstanding balance per month, whichever is greater. The Company reserves the right to suspend services for any account more than sixty (60) days past due.

**C. Returned Payments.** A fee of $35.00 will be assessed for any returned check or failed electronic payment (NSF fee).

**D. Collection Costs.** If the Company refers any unpaid balance to collections or retains legal counsel to collect amounts due, the Customer agrees to pay all reasonable collection costs, attorney's fees, and court costs incurred.

**E. Price Adjustments.** The Company may adjust pricing annually, not to exceed 5% per year, by providing written notice at least thirty (30) days before the renewal date. If the Customer does not cancel within the cancellation window after receiving notice of a price adjustment, the adjusted price shall apply to the renewal term.

**F. Taxes.** All prices are exclusive of applicable sales tax. Customer is responsible for any taxes imposed on services provided under this Agreement.
"""

SHARED_LIABILITY = """
## LIABILITY LIMITATIONS & WARRANTY DISCLAIMERS

**A. Limited Warranty.** The Company warrants that all services will be performed in a professional and workmanlike manner consistent with industry standards. This warranty is limited to re-performance of any deficient service within thirty (30) days of the original service date, at no additional charge.

**B. DISCLAIMER.** EXCEPT AS EXPRESSLY STATED IN THIS AGREEMENT, THE COMPANY MAKES NO WARRANTIES, EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION ANY IMPLIED WARRANTIES OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE. THE COMPANY DOES NOT WARRANT THAT THE SYSTEM WILL OPERATE WITHOUT INTERRUPTION OR MALFUNCTION.

**C. Limitation of Liability.** THE COMPANY'S TOTAL LIABILITY UNDER THIS AGREEMENT, WHETHER IN CONTRACT, TORT, OR OTHERWISE, SHALL NOT EXCEED THE TOTAL AMOUNT PAID BY THE CUSTOMER UNDER THIS AGREEMENT DURING THE TWELVE (12) MONTHS PRECEDING THE CLAIM. IN NO EVENT SHALL THE COMPANY BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING BUT NOT LIMITED TO PROPERTY DAMAGE, LOSS OF USE, LOST PROFITS, OR ENVIRONMENTAL REMEDIATION COSTS.

**D. Pre-Existing Conditions.** The Company is not responsible for pre-existing defects, damage, or non-compliance of the System that existed prior to the commencement of this Agreement. The Company's maintenance obligations are limited to routine maintenance as described in the Scope of Services and do not include repair or replacement of failed components unless separately contracted.

**E. Force Majeure.** Neither party shall be liable for any failure or delay in performance caused by circumstances beyond its reasonable control, including but not limited to: acts of God, natural disasters, floods, drought, fire, pandemic, epidemic, government orders or regulations, labor disputes, supply chain disruptions, power outages, or any other event that could not reasonably be anticipated or prevented. The affected party's obligations shall be suspended for the duration of the force majeure event.

**F. Third-Party Actions.** The Company shall not be liable for damage caused by third parties, the Customer, the Customer's tenants, guests, or contractors, or by the Customer's failure to follow the Company's recommendations.
"""

SHARED_INDEMNIFICATION = """
## INDEMNIFICATION

**A. Customer Indemnification.** The Customer agrees to indemnify, defend, and hold harmless the Company, its owners, officers, employees, agents, and subcontractors from and against any and all claims, damages, losses, liabilities, costs, and expenses (including reasonable attorney's fees) arising out of or related to:

1. The Customer's breach of this Agreement;
2. The Customer's negligence or willful misconduct;
3. Any misrepresentation by the Customer regarding the System, property, or access conditions;
4. Any environmental contamination, property damage, or personal injury caused by the System's malfunction that is not directly attributable to the Company's negligence;
5. Any claim by a third party related to the Customer's property or System.

**B. Survival.** This indemnification obligation shall survive the termination or expiration of this Agreement.
"""

SHARED_DISPUTE_RESOLUTION = """
## DISPUTE RESOLUTION

**A. Informal Resolution.** The parties agree to first attempt to resolve any dispute arising under this Agreement through good-faith negotiation. Either party may initiate this process by providing written notice of the dispute to the other party.

**B. Mediation.** If the dispute is not resolved within thirty (30) days of the initial notice, either party may request mediation. Mediation shall be conducted in Hays County, Texas, by a mutually agreed-upon mediator. The costs of mediation shall be shared equally.

**C. Binding Arbitration.** If mediation fails to resolve the dispute within sixty (60) days, the dispute shall be submitted to binding arbitration in Hays County, Texas, administered under the rules of the American Arbitration Association. The arbitrator's decision shall be final and binding, and judgment on the award may be entered in any court of competent jurisdiction.

**D. Governing Law.** This Agreement shall be governed by and construed in accordance with the laws of the State of Texas, without regard to conflict of law principles.

**E. Venue.** For any matter not subject to arbitration, the exclusive venue shall be in the courts of Hays County, Texas.

**F. Attorney's Fees.** In any legal proceeding arising out of this Agreement, the prevailing party shall be entitled to recover reasonable attorney's fees and costs from the non-prevailing party.

**G. Class Action Waiver.** The Customer agrees that any dispute shall be brought solely in the Customer's individual capacity, and not as a plaintiff or class member in any purported class, consolidated, or representative proceeding.
"""

SHARED_GENERAL_PROVISIONS = """
## GENERAL PROVISIONS

**A. Entire Agreement.** This Agreement constitutes the entire agreement between the parties and supersedes all prior or contemporaneous agreements, representations, and understandings, whether written or oral.

**B. Amendments.** This Agreement may not be amended except by a written instrument signed by both parties.

**C. Severability.** If any provision of this Agreement is held invalid or unenforceable, the remaining provisions shall continue in full force and effect.

**D. Waiver.** The failure of either party to enforce any provision of this Agreement shall not constitute a waiver of that provision or any other provision.

**E. Assignment.** The Company may assign this Agreement to a successor entity without the Customer's consent. The Customer may not assign this Agreement without the Company's prior written consent.

**F. Notices.** All notices shall be in writing and sent to the addresses specified above, by certified mail, email, or hand delivery.

**G. County Filing Requirement.** The Customer acknowledges that Texas TCEQ regulations (30 TAC Chapter 285) may require that a maintenance contract be filed with the Permitting Authority (county health department) for aerobic treatment units and certain other OSSF systems. The Company will file this Agreement with the applicable Permitting Authority on the Customer's behalf. Failure to maintain a valid maintenance contract may result in violations, fines, or enforcement actions by the county.

**H. Access.** The Customer agrees to provide the Company reasonable access to the System and property for all scheduled and emergency services. If the Company is unable to access the property for a scheduled visit, the visit will be rescheduled and an additional trip charge of $75.00 may apply.

**I. Hazardous Conditions.** The Company reserves the right to refuse or suspend service if hazardous conditions exist at the Service Address, including but not limited to aggressive animals, unsafe terrain, contamination, or any condition that poses a risk to Company personnel.

**J. Independent Contractor.** The Company is an independent contractor and nothing in this Agreement creates an employer-employee relationship, partnership, or joint venture.

**K. Survival.** All provisions of this Agreement that by their nature should survive termination shall survive, including but not limited to: payment obligations, indemnification, limitation of liability, and dispute resolution.
"""

# ============================================================
# CONTRACT 1: Initial 2-Year Aerobic Contract with Evergreen Renewal
# ============================================================

CONTRACT_1_INITIAL_2YR = """
# MAC SEPTIC SERVICES
## INITIAL 2-YEAR AEROBIC SYSTEM MAINTENANCE AGREEMENT
### With Automatic Evergreen Renewal

---

**Agreement Number:** {{contract_number}}
**Effective Date:** {{start_date}}
**Customer:** {{customer_name}}
**Service Address:** {{service_address}}
**System Type:** Aerobic Treatment Unit (ATU)

---

## RECITALS

WHEREAS, the Customer owns property at the Service Address with an on-site sewage facility (OSSF) that includes an aerobic treatment unit; and

WHEREAS, Texas law (30 TAC Chapter 285) requires that aerobic treatment units be maintained under a valid maintenance contract with a licensed maintenance provider; and

WHEREAS, the Company is a TCEQ-licensed maintenance provider qualified to service aerobic treatment systems in the State of Texas;

NOW, THEREFORE, in consideration of the mutual promises and covenants contained herein, the parties agree as follows:

""" + SHARED_DEFINITIONS + """

## TERM & RENEWAL

**A. Initial Term.** This Agreement has an initial term of twenty-four (24) months, beginning on the Effective Date ("Initial Term").

**B. Automatic Renewal.** Upon expiration of the Initial Term, this Agreement shall **automatically renew** for successive twelve (12) month terms ("Renewal Terms") under the same terms and conditions, unless terminated in accordance with this section.

**C. Cancellation Window.** Either party may terminate this Agreement by providing **written notice at least sixty (60) days** before the end of the current term (Initial Term or any Renewal Term). If notice is not received within this window, the Agreement shall automatically renew.

**D. Cancellation Notice.** Cancellation requests must be submitted in writing via certified mail, email to contracts@macseptic.com, or through the customer portal. Phone requests alone are not sufficient.

**E. Early Termination Fee — Initial Term.** If the Customer terminates this Agreement during the Initial Term for any reason other than the Company's material breach, the Customer agrees to pay an early termination fee equal to **50% of the remaining contract value** for the Initial Term. This fee reflects the Company's discounted pricing for the 2-year commitment, initial system evaluation costs, county filing fees, and reserved scheduling capacity.

**F. Early Termination Fee — Renewal Terms.** If the Customer terminates during a Renewal Term outside the cancellation window, the Customer agrees to pay an early termination fee equal to **$150.00** or **three (3) months of the annualized contract value**, whichever is less.

**G. Effect of Termination.** Upon termination, the Customer is responsible for all amounts due through the termination date plus any applicable early termination fees. The Company will notify the Permitting Authority of the contract termination as required by TCEQ regulations.

## SCOPE OF SERVICES

**A. Included Services.** During the term of this Agreement, the Company shall provide:

1. **Routine Maintenance Visits** — Three (3) visits per year (approximately every four months), including:
   - Visual inspection of all aerobic system components
   - Testing of effluent quality (chlorine residual, clarity)
   - Inspection and adjustment of spray heads/drip lines
   - Air compressor/aerator inspection and testing
   - Alarm system testing
   - Chlorine/disinfection tablet replenishment (up to standard dosage)
   - Minor adjustments to timers, floats, and controls
   - Sludge level measurement

2. **TCEQ Compliance Reporting** — Filing of all required maintenance reports with the Permitting Authority, including the Texas OSSF Maintenance Report (TCEQ Form 0637).

3. **Emergency Phone Support** — Telephone troubleshooting during business hours (Mon–Fri, 8am–5pm) at no additional charge.

4. **Priority Scheduling** — As a contract customer, the Customer receives priority scheduling for all service requests, typically within 24–48 hours.

5. **Annual System Health Report** — A written summary of system condition, recommendations, and projected needs, delivered annually.

**B. Excluded Services.** The following are NOT included and will be billed separately at the Company's then-current rates:

1. Emergency or after-hours service calls (nights, weekends, holidays)
2. Repair or replacement of system components (pumps, compressors, control panels, tanks, spray heads, drip lines, etc.)
3. Septic tank pumping/cleaning (available at a discounted contract rate)
4. Electrical work or plumbing beyond the System
5. Root removal, excavation, or landscaping
6. Damage caused by third parties, acts of God, or Customer negligence
7. System modifications, upgrades, or code compliance corrections
8. Permit applications or engineering services
9. Service calls resulting from power outages, lightning strikes, or electrical surges

## PRICING

**A. Contract Price.** The total price for the Initial Term (24 months) is **$575.00**, payable as follows:

- **Option 1:** Single payment of $575.00 due at signing
- **Option 2:** Two annual payments of $300.00 (Year 1) and $300.00 (Year 2), totaling $600.00
- **Option 3:** Monthly payments of $26.00/month ($624.00 total) via autopay

**B. Renewal Pricing.** Renewal Terms shall be at the Company's then-current annual rate for this service level, subject to the annual price adjustment provision.

**C. Contract Customer Discounts.** As a valued contract customer, you receive:
- **15% discount** on all parts and repairs
- **$50 off** any septic tank pumping service
- **Free** annual system health report (valued at $95)
- **Priority scheduling** — ahead of non-contract customers
- **Price lock guarantee** — no more than 5% annual increase

## LOYALTY REWARDS

- After **2 consecutive years**: Free system camera inspection (value $150)
- After **3 consecutive years**: One free emergency service call per year (value up to $195)
- After **5 consecutive years**: Free aerator/compressor preventive replacement (value up to $350)
- **Referral bonus**: $50 credit for each new customer you refer who signs a contract

""" + SHARED_PAYMENT_TERMS + SHARED_LIABILITY + SHARED_INDEMNIFICATION + SHARED_DISPUTE_RESOLUTION + SHARED_GENERAL_PROVISIONS + """

## CUSTOMER ACKNOWLEDGMENTS

By signing below, the Customer acknowledges and agrees that:

1. I have read and understand all terms of this Agreement.
2. I understand that this Agreement will **automatically renew** unless I provide written cancellation notice at least **60 days** before the end of the current term.
3. I understand that **early termination fees** apply as described above.
4. I authorize the Company to file this maintenance contract with the Permitting Authority as required by TCEQ regulations.
5. I authorize the Company to charge the payment method on file for all amounts due.
6. I understand that maintaining a valid maintenance contract is required by Texas law for aerobic treatment systems.

---

**CUSTOMER SIGNATURE**

Signature: _____________________________ Date: ____________

Print Name: {{customer_name}}

**MAC SEPTIC SERVICES, LLC**

Signature: _____________________________ Date: ____________

Print Name: _____________________________ Title: _____________
"""


# ============================================================
# CONTRACT 2: Evergreen Maintenance Contract ($300/year)
# ============================================================

CONTRACT_2_EVERGREEN_MAINT = """
# MAC SEPTIC SERVICES
## EVERGREEN MAINTENANCE AGREEMENT
### Continuous Coverage with Automatic Renewal

---

**Agreement Number:** {{contract_number}}
**Effective Date:** {{start_date}}
**Customer:** {{customer_name}}
**Service Address:** {{service_address}}
**System Type:** {{system_type}}

---

## RECITALS

WHEREAS, the Customer desires ongoing maintenance and monitoring of their on-site sewage facility; and

WHEREAS, the Company is qualified to provide professional septic system maintenance services in the State of Texas;

NOW, THEREFORE, in consideration of the mutual promises and covenants contained herein, the parties agree as follows:

""" + SHARED_DEFINITIONS + """

## TERM & RENEWAL

**A. Initial Term.** This Agreement has an initial term of twelve (12) months, beginning on the Effective Date.

**B. Automatic Renewal.** This Agreement shall **automatically renew** for successive twelve (12) month terms under the same terms and conditions, unless terminated in accordance with this section. **This is a continuous, evergreen agreement designed to provide uninterrupted protection for your system.**

**C. Cancellation Window.** Either party may terminate this Agreement by providing **written notice at least sixty (60) days** before the end of the current term. If timely notice is not received, the Agreement shall automatically renew for the next term.

**D. Cancellation Notice.** Cancellation requests must be submitted in writing via certified mail, email to contracts@macseptic.com, or through the customer portal.

**E. Early Termination Fee.** If the Customer terminates this Agreement outside the cancellation window, the Customer agrees to pay an early termination fee of **$100.00**. This fee compensates the Company for scheduling commitments and administrative costs.

**F. Effect of Termination.** Upon termination, the Customer is responsible for all amounts due through the termination date plus any applicable fees. For aerobic systems, the Company will notify the Permitting Authority as required.

## SCOPE OF SERVICES

**A. Included Services:**

1. **Two (2) Maintenance Visits Per Year** (approximately every six months), including:
   - Comprehensive system inspection
   - Effluent quality assessment
   - Component function testing
   - Disinfection replenishment (aerobic systems)
   - Float and switch inspection
   - Minor adjustments and calibration
   - Written service report

2. **TCEQ Compliance Reporting** (for systems requiring maintenance contracts)
3. **Phone Support** during business hours
4. **Priority Scheduling** — within 48 hours for service requests

**B. Excluded Services:**

1. Emergency/after-hours calls
2. Repairs, parts, or component replacement
3. Tank pumping (discounted rate available)
4. Electrical, plumbing, or excavation work
5. Damage from third parties or acts of God
6. System modifications or upgrades

## PRICING

**A. Annual Fee.** **$300.00** per year, payable as follows:

- **Option 1:** Single annual payment of $300.00
- **Option 2:** Monthly autopay of $27.00/month ($324.00/year)

**B. Contract Customer Benefits:**
- **10% discount** on all repairs and parts
- **$40 off** septic tank pumping
- **Priority scheduling** over non-contract customers
- **No trip charges** for scheduled visits

## LOYALTY REWARDS

- After **2 consecutive years**: Free drain field inspection (value $125)
- After **3 consecutive years**: Upgrade to 3 visits/year at no extra cost for one year
- **Referral bonus**: $40 credit per referred customer who signs a contract

""" + SHARED_PAYMENT_TERMS + SHARED_LIABILITY + SHARED_INDEMNIFICATION + SHARED_DISPUTE_RESOLUTION + SHARED_GENERAL_PROVISIONS + """

## CUSTOMER ACKNOWLEDGMENTS

By signing below, the Customer acknowledges and agrees that:

1. I have read and understand all terms of this Agreement.
2. I understand this is an **evergreen agreement** that **automatically renews** annually unless I provide written cancellation notice at least **60 days** before the end of the current term.
3. I understand that early termination fees apply as described above.
4. I authorize the Company to charge the payment method on file for all amounts due.

---

**CUSTOMER SIGNATURE**

Signature: _____________________________ Date: ____________

Print Name: {{customer_name}}

**MAC SEPTIC SERVICES, LLC**

Signature: _____________________________ Date: ____________

Print Name: _____________________________ Title: _____________
"""


# ============================================================
# CONTRACT 3: Standard Yearly Maintenance Contract ($350/year)
# ============================================================

CONTRACT_3_YEARLY_MAINT = """
# MAC SEPTIC SERVICES
## STANDARD YEARLY MAINTENANCE AGREEMENT

---

**Agreement Number:** {{contract_number}}
**Effective Date:** {{start_date}}
**Customer:** {{customer_name}}
**Service Address:** {{service_address}}
**System Type:** {{system_type}}

---

## RECITALS

WHEREAS, the Customer desires professional maintenance of their on-site sewage facility; and

WHEREAS, the Company is qualified to provide comprehensive septic system maintenance in the State of Texas;

NOW, THEREFORE, in consideration of the mutual promises and covenants contained herein, the parties agree as follows:

""" + SHARED_DEFINITIONS + """

## TERM & RENEWAL

**A. Term.** This Agreement has a term of twelve (12) months, beginning on the Effective Date.

**B. Renewal.** At the end of the term, this Agreement shall **automatically renew** for successive twelve (12) month terms unless either party provides **written notice at least sixty (60) days** before the end of the current term.

**C. Cancellation.** Cancellation requests must be submitted in writing via certified mail, email to contracts@macseptic.com, or through the customer portal.

**D. Early Termination.** If the Customer terminates this Agreement outside the cancellation window, the Customer agrees to pay an early termination fee of **$125.00**.

## SCOPE OF SERVICES

**A. Included Services:**

1. **Three (3) Maintenance Visits Per Year** (approximately every four months), including:
   - Full system inspection and performance assessment
   - Effluent quality testing and documentation
   - Spray head/distribution inspection and adjustment
   - Aerator/compressor function testing
   - Alarm and safety system verification
   - Chlorine/disinfection maintenance
   - Sludge level assessment with pumping recommendation
   - Timer and control verification
   - Written service report after each visit

2. **TCEQ Compliance** — All required reporting and filings
3. **Phone Support** — Business hours troubleshooting
4. **Priority Scheduling** — 24-hour response for contract customers
5. **Annual System Health Report** with recommendations

**B. Excluded Services:**

1. Emergency/after-hours service calls
2. Repairs, parts, or component replacement
3. Tank pumping (contract rate: $50 off standard pricing)
4. Electrical, plumbing, excavation, or landscaping
5. Damage from misuse, neglect, third parties, or force majeure
6. System modifications, upgrades, or engineering

## PRICING

**A. Annual Fee.** **$350.00** per year, payable as follows:

- **Option 1:** Single annual payment of $350.00
- **Option 2:** Semi-annual payments of $185.00 ($370.00/year)
- **Option 3:** Monthly autopay of $32.00/month ($384.00/year)

**B. Contract Customer Benefits:**
- **15% discount** on all repairs and parts
- **$50 off** any pumping service
- **Priority scheduling** — same-day or next-day for urgencies
- **Free annual system health report** (value $95)
- **No trip charges** for all scheduled visits

## LOYALTY REWARDS

- After **2 years**: Free camera inspection (value $150)
- After **3 years**: One free emergency call per year (value $195)
- After **5 years**: Complimentary aerator preventive replacement (value up to $350)
- **Referral bonus**: $50 credit per referred customer

""" + SHARED_PAYMENT_TERMS + SHARED_LIABILITY + SHARED_INDEMNIFICATION + SHARED_DISPUTE_RESOLUTION + SHARED_GENERAL_PROVISIONS + """

## CUSTOMER ACKNOWLEDGMENTS

By signing below, the Customer acknowledges and agrees that:

1. I have read and understand all terms of this Agreement.
2. I understand this Agreement **automatically renews** unless I provide written cancellation notice at least **60 days** before the end of the term.
3. I understand that early termination fees apply as described above.
4. I authorize the Company to charge the payment method on file.

---

**CUSTOMER SIGNATURE**

Signature: _____________________________ Date: ____________

Print Name: {{customer_name}}

**MAC SEPTIC SERVICES, LLC**

Signature: _____________________________ Date: ____________

Print Name: _____________________________ Title: _____________
"""


# ============================================================
# CONTRACT 4: Evergreen Service Visit Plans
# ============================================================

CONTRACT_4_SERVICE_VISITS = """
# MAC SEPTIC SERVICES
## EVERGREEN SERVICE VISIT PLAN
### Flexible Maintenance with Automatic Renewal

---

**Agreement Number:** {{contract_number}}
**Effective Date:** {{start_date}}
**Customer:** {{customer_name}}
**Service Address:** {{service_address}}
**System Type:** {{system_type}}

**Plan Selected:** {{plan_tier}}

| Plan | Annual Visits | Annual Price |
|------|:---:|---:|
| Essential (1 Visit) | 1 | $175.00 |
| Standard (2 Visits) | 2 | $295.00 |
| Premium (3 Visits) | 3 | $325.00 |

---

## RECITALS

WHEREAS, the Customer desires flexible, ongoing maintenance of their on-site sewage facility; and

WHEREAS, the Company offers tiered service visit plans to accommodate varying system needs;

NOW, THEREFORE, in consideration of the mutual promises and covenants contained herein, the parties agree as follows:

""" + SHARED_DEFINITIONS + """

## TERM & RENEWAL

**A. Initial Term.** This Agreement has an initial term of twelve (12) months, beginning on the Effective Date.

**B. Automatic Renewal.** This Agreement shall **automatically renew** for successive twelve (12) month terms under the same plan tier and terms, unless terminated in accordance with this section. This is a continuous evergreen agreement.

**C. Cancellation.** Either party may terminate by providing **written notice at least sixty (60) days** before the end of the current term.

**D. Plan Changes.** The Customer may upgrade to a higher-tier plan at any time by paying the prorated difference. Downgrades take effect at the next renewal.

**E. Early Termination Fee.** If the Customer terminates outside the cancellation window, the Customer agrees to pay an early termination fee of **$75.00** (Essential), **$100.00** (Standard), or **$125.00** (Premium).

## SCOPE OF SERVICES — BY PLAN TIER

### Essential Plan (1 Visit/Year — $175.00)

1. **One (1) Annual Maintenance Visit**, including:
   - Complete system inspection
   - Effluent quality check
   - Component function testing
   - Disinfection replenishment
   - Written service report

2. TCEQ compliance reporting (if applicable)
3. Phone support during business hours

### Standard Plan (2 Visits/Year — $295.00)

All Essential Plan services, PLUS:

1. **Two (2) Maintenance Visits Per Year** (approximately every 6 months)
2. Priority scheduling (within 48 hours)
3. **10% discount** on repairs and parts
4. **$30 off** pumping services

### Premium Plan (3 Visits/Year — $325.00)

All Standard Plan services, PLUS:

1. **Three (3) Maintenance Visits Per Year** (approximately every 4 months)
2. **Priority scheduling** (within 24 hours)
3. **15% discount** on repairs and parts
4. **$50 off** pumping services
5. **Free annual system health report** (value $95)
6. **No trip charges** on any visit

## EXCLUDED SERVICES (All Plans)

1. Emergency/after-hours service calls
2. Repairs, parts, or component replacement (discounted for Standard/Premium)
3. Tank pumping (discounted for Standard/Premium)
4. Electrical, plumbing, excavation work
5. Damage from misuse, neglect, or force majeure
6. System modifications or upgrades

## PRICING

The annual fee for the selected plan tier is due as follows:

- **Option 1:** Single annual payment
- **Option 2:** Monthly autopay (Essential: $16.00/mo; Standard: $27.00/mo; Premium: $30.00/mo)

## LOYALTY REWARDS

- After **2 consecutive years**: Free upgrade to next tier for one year
- After **3 consecutive years on Premium**: One free emergency call per year
- **Referral bonus**: $25 credit (Essential), $40 credit (Standard), $50 credit (Premium)

""" + SHARED_PAYMENT_TERMS + SHARED_LIABILITY + SHARED_INDEMNIFICATION + SHARED_DISPUTE_RESOLUTION + SHARED_GENERAL_PROVISIONS + """

## CUSTOMER ACKNOWLEDGMENTS

By signing below, the Customer acknowledges and agrees that:

1. I have selected the **{{plan_tier}}** plan.
2. I understand this is an **evergreen agreement** that **automatically renews** annually.
3. Written cancellation notice of at least **60 days** is required before the end of any term.
4. Early termination fees apply as described above.
5. I authorize the Company to charge the payment method on file.

---

**CUSTOMER SIGNATURE**

Signature: _____________________________ Date: ____________

Print Name: {{customer_name}}

**MAC SEPTIC SERVICES, LLC**

Signature: _____________________________ Date: ____________

Print Name: _____________________________ Title: _____________
"""


# ============================================================
# CONTRACT 5: Commercial Septic Maintenance Contract
# ============================================================

CONTRACT_5_COMMERCIAL = """
# MAC SEPTIC SERVICES
## COMMERCIAL SEPTIC SYSTEM MAINTENANCE AGREEMENT

---

**Agreement Number:** {{contract_number}}
**Effective Date:** {{start_date}}
**Business Name:** {{customer_name}}
**Contact Person:** {{contact_person}}
**Service Address:** {{service_address}}
**System Type:** {{system_type}}
**System Capacity:** {{system_capacity}}

**Tier Selected:** {{commercial_tier}}

| Tier | Tank Capacity | Visits/Year | Monthly | Annual |
|------|:---:|:---:|---:|---:|
| Small Business | Up to 1,500 gal | 4 | $75.00 | $850.00 |
| Medium Commercial | 1,501–5,000 gal | 6 | $125.00 | $1,400.00 |
| Large Commercial | 5,001+ gal | 12 | $200.00 | $2,200.00 |

---

## RECITALS

WHEREAS, the Customer operates a commercial establishment with an on-site sewage facility; and

WHEREAS, commercial OSSF systems require more frequent maintenance due to higher usage volumes; and

WHEREAS, failure to maintain a commercial OSSF may result in TCEQ enforcement, county violations, health department closures, and significant liability;

NOW, THEREFORE, in consideration of the mutual promises and covenants contained herein, the parties agree as follows:

""" + SHARED_DEFINITIONS + """

## TERM & RENEWAL

**A. Initial Term.** This Agreement has an initial term of twenty-four (24) months ("Initial Term"), reflecting the investment required to establish a comprehensive maintenance program for commercial systems.

**B. Automatic Renewal.** Upon expiration of the Initial Term, this Agreement shall **automatically renew** for successive twelve (12) month terms unless terminated in accordance with this section.

**C. Cancellation Window.** Either party may terminate by providing **written notice at least ninety (90) days** before the end of the current term.

**D. Early Termination — Initial Term.** If the Customer terminates during the Initial Term, the Customer agrees to pay an early termination fee equal to **50% of the remaining contract value** for the Initial Term.

**E. Early Termination — Renewal Terms.** If the Customer terminates during a Renewal Term outside the cancellation window, the Customer agrees to pay an early termination fee equal to **three (3) months** of the annual contract value.

**F. Transition Assistance.** Upon termination, the Company will provide reasonable transition documentation to a successor maintenance provider within thirty (30) days, including system records and maintenance history.

## SCOPE OF SERVICES — BY TIER

### Small Business Tier (Up to 1,500 gallon system — $850/year)

1. **Four (4) Maintenance Visits Per Year** (quarterly), including:
   - Comprehensive system inspection and testing
   - Effluent quality analysis and documentation
   - All component function verification
   - Disinfection system maintenance
   - Grease trap inspection (if applicable)
   - Written compliance report

2. TCEQ compliance reporting and county filings
3. **24/7 Emergency phone line** — response within 4 hours during business hours
4. Priority scheduling — within 24 hours
5. Quarterly system performance report
6. Annual comprehensive health assessment

### Medium Commercial Tier (1,501–5,000 gallon system — $1,400/year)

All Small Business Tier services, PLUS:

1. **Six (6) Maintenance Visits Per Year** (every two months)
2. **Grease trap maintenance** included (one cleaning per year)
3. **Same-day emergency response** during business hours
4. **20% discount** on all repairs, parts, and pumping
5. Semi-annual management reports
6. **Dedicated account manager**

### Large Commercial Tier (5,001+ gallon system — $2,200/year)

All Medium Commercial Tier services, PLUS:

1. **Twelve (12) Maintenance Visits Per Year** (monthly)
2. **Grease trap maintenance** — up to four (4) cleanings per year
3. **4-hour emergency response guarantee** (24/7)
4. **25% discount** on all repairs, parts, and pumping
5. Monthly system performance dashboards
6. **Annual system optimization review** by senior technician
7. **One (1) complimentary pumping per year** (value up to $500)

## EXCLUDED SERVICES (All Tiers)

1. Major repairs or system replacement (discounted rates apply)
2. Excavation, landscaping, or structural work
3. Electrical work beyond the system controls
4. Damage from misuse, vandalism, or force majeure
5. System redesign, engineering, or permit applications
6. Environmental remediation or contamination cleanup
7. Third-party damage or customer-caused issues

## PRICING

The annual fee for the selected tier is payable as follows:

- **Option 1:** Single annual payment (5% discount: Small $807.50, Medium $1,330.00, Large $2,090.00)
- **Option 2:** Quarterly payments
- **Option 3:** Monthly autopay at listed monthly rate

## COMMERCIAL LOYALTY PROGRAM

- After **2 consecutive years**: Free system camera inspection + written evaluation
- After **3 consecutive years**: One tier upgrade for free for one year
- **Multi-location discount**: 10% off each additional location
- **Referral program**: $100 credit per referred commercial customer

## COMMERCIAL-SPECIFIC PROVISIONS

**A. Business Continuity.** The Company understands the critical nature of commercial OSSF operations. Service interruptions can result in business closures and revenue loss. The Company commits to prioritizing commercial accounts for emergency response.

**B. Compliance Documentation.** The Company will maintain and provide documentation suitable for health department inspections, insurance audits, and regulatory compliance reviews.

**C. Insurance.** The Company maintains commercial general liability insurance of not less than $1,000,000 per occurrence. Certificate of insurance available upon request.

**D. Confidentiality.** The Company agrees to maintain the confidentiality of the Customer's business information and system records.

""" + SHARED_PAYMENT_TERMS + SHARED_LIABILITY + SHARED_INDEMNIFICATION + SHARED_DISPUTE_RESOLUTION + SHARED_GENERAL_PROVISIONS + """

## CUSTOMER ACKNOWLEDGMENTS

By signing below, the authorized representative of the Customer acknowledges and agrees that:

1. I am authorized to enter into this Agreement on behalf of the business.
2. I have selected the **{{commercial_tier}}** tier.
3. This Agreement has a **24-month Initial Term** and **automatically renews** for 12-month terms thereafter.
4. Written cancellation requires at least **90 days** notice before the end of any term.
5. Early termination fees apply as described above.
6. I authorize the Company to charge the payment method on file.

---

**CUSTOMER / AUTHORIZED REPRESENTATIVE**

Signature: _____________________________ Date: ____________

Print Name: {{contact_person}}

Title: _____________________________

Business: {{customer_name}}

**MAC SEPTIC SERVICES, LLC**

Signature: _____________________________ Date: ____________

Print Name: _____________________________ Title: _____________
"""


# ============================================================
# SUMMARY TABLE & RECOMMENDATIONS
# ============================================================

CONTRACT_SUMMARY = """
# MAC Septic Services — Contract Comparison Summary

| Feature | Initial 2-Year | Evergreen Maint. | Standard Yearly | Service Visit Plans | Commercial |
|---------|:-:|:-:|:-:|:-:|:-:|
| **Price** | $575 (2yr) | $300/yr | $350/yr | $175/$295/$325 | $850/$1,400/$2,200 |
| **Initial Term** | 24 months | 12 months | 12 months | 12 months | 24 months |
| **Auto-Renew** | Yes (12mo) | Yes (12mo) | Yes (12mo) | Yes (12mo) | Yes (12mo) |
| **Cancel Notice** | 60 days | 60 days | 60 days | 60 days | 90 days |
| **Early Term Fee** | 50% remaining | $100 | $125 | $75-$125 | 50% remaining (initial) |
| **Visits/Year** | 3 | 2 | 3 | 1/2/3 | 4/6/12 |
| **Parts Discount** | 15% | 10% | 15% | 0%/10%/15% | 20%/25% |
| **Pumping Discount** | $50 off | $40 off | $50 off | $0/$30/$50 | 20-25% off |
| **Priority Sched.** | 24-48hr | 48hr | 24hr | No/48hr/24hr | 24hr/Same-day/4hr |
| **TCEQ Filing** | Included | Included | Included | If applicable | Included |
| **Loyalty Rewards** | Yes | Yes | Yes | Yes | Yes |
"""

PRICING_RECOMMENDATIONS = """
# Pricing & Retention Strategy Recommendations

## Maximize Lifetime Value

1. **Push the 2-Year Initial Contract**: This is your highest-value play. The 2-year commitment + evergreen renewal creates a customer for 3+ years on average. The $575 price is below market ($300/yr equivalent vs $350 standard). Position as "best value" — customers save $125 over 2 years vs yearly.

2. **Default to Evergreen**: Every contract should auto-renew. The 60-day written cancellation window creates significant friction. Most customers will forget or delay, resulting in automatic renewal.

3. **Monthly Autopay is Key**: Customers on monthly autopay have 3x lower churn than annual payers. The slight premium ($624 vs $575 for 2-year) is worth it for the retention benefit.

4. **Loyalty Rewards Prevent Switching**: The tiered loyalty program (free camera inspection at 2yr, free emergency call at 3yr, free equipment at 5yr) creates increasing switching costs. Customers who have "earned" benefits are much less likely to cancel.

## Pricing Adjustments to Consider

1. **Raise Standard Yearly to $375**: The $350 price is below market for 3 visits/year with TCEQ filing. A $375 price still undercuts competitors while improving margin.

2. **Add a "Premium Residential" tier at $450/yr**: Include 4 visits + one pumping discount. Targets high-value homeowners who want maximum protection.

3. **Commercial pricing is competitive but could be higher**: Consider $950/$1,500/$2,400 for the three tiers. Commercial customers value reliability over price, and your 24/7 emergency response has significant value.

4. **Monthly autopay premium should be 8-10%**: Currently the monthly option costs ~8.5% more than annual. This is optimal — just enough to incentivize annual payment while keeping monthly accessible.

## Retention Strategies

1. **60-day cancellation window**: This is the single most effective retention tool. By the time customers think about cancelling, they're usually past the window.

2. **Early termination fees**: The 50% remaining value fee on 2-year contracts is aggressive but defensible — frame it as a "commitment discount recovery."

3. **County filing dependency**: Remind customers that cancelling means they need to find another licensed provider and re-file with the county. This friction alone prevents many cancellations.

4. **Annual price lock guarantee (5% cap)**: This creates perceived value and removes a common cancellation trigger (price shock).

5. **Referral program**: Customers who refer others are 4x less likely to cancel themselves. The $50 credit is cheap insurance.
"""


# ============================================================
# MAP TEMPLATES TO SEED DATA
# ============================================================

MAC_SEPTIC_CONTRACT_TEMPLATES = [
    {
        "code": "INIT_2YR_EVERGREEN",
        "name": "Initial 2-Year Aerobic Evergreen",
        "description": "Initial 2-year evergreen maintenance contract for new customers. Includes comprehensive septic system inspection, pumping, and preventive maintenance. Best value for long-term coverage.",
        "contract_type": "multi-year",
        "default_duration_months": 24,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "base_price": 575.00,
        "content": CONTRACT_1_INITIAL_2YR,
        "terms_and_conditions": "24-month initial term with automatic 12-month renewal. 60 days written cancellation notice required. Early termination fee: 50% of remaining contract value during initial term; $150 during renewal terms.",
        "default_services": [
            {"service_code": "MAINT-ATU", "description": "Aerobic system maintenance visit", "frequency": "tri-annual", "quantity": 3},
            {"service_code": "TCEQ-FILE", "description": "TCEQ compliance reporting", "frequency": "annual", "quantity": 1},
            {"service_code": "HEALTH-RPT", "description": "Annual system health report", "frequency": "annual", "quantity": 1},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "service_address"],
    },
    {
        "code": "EVERGREEN_MAINT",
        "name": "Evergreen Maintenance",
        "description": "Evergreen maintenance contract with automatic renewal. Budget-friendly option for ongoing system care with 2 visits per year.",
        "contract_type": "maintenance",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "base_price": 300.00,
        "content": CONTRACT_2_EVERGREEN_MAINT,
        "terms_and_conditions": "12-month term with automatic annual renewal. 60 days written cancellation notice required. Early termination fee: $100.",
        "default_services": [
            {"service_code": "MAINT-STD", "description": "Standard maintenance visit", "frequency": "semi-annual", "quantity": 2},
            {"service_code": "TCEQ-FILE", "description": "TCEQ compliance reporting", "frequency": "annual", "quantity": 1},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "service_address", "system_type"],
    },
    {
        "code": "YEARLY_MAINT",
        "name": "Standard Yearly Maintenance",
        "description": "Standard annual maintenance contract. Three service visits per year including pumping recommendation and full inspection.",
        "contract_type": "annual",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "base_price": 350.00,
        "content": CONTRACT_3_YEARLY_MAINT,
        "terms_and_conditions": "12-month term with automatic annual renewal. 60 days written cancellation notice required. Early termination fee: $125.",
        "default_services": [
            {"service_code": "MAINT-FULL", "description": "Full maintenance visit with testing", "frequency": "tri-annual", "quantity": 3},
            {"service_code": "TCEQ-FILE", "description": "TCEQ compliance reporting", "frequency": "annual", "quantity": 1},
            {"service_code": "HEALTH-RPT", "description": "Annual system health report", "frequency": "annual", "quantity": 1},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "service_address", "system_type"],
    },
    {
        "code": "EVERGREEN_SVC_1",
        "name": "Evergreen Service - 1 Visit",
        "description": "Evergreen service contract with 1 annual visit. Ideal for low-usage residential systems. Essential coverage at the best price.",
        "contract_type": "service",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "base_price": 175.00,
        "content": CONTRACT_4_SERVICE_VISITS,
        "terms_and_conditions": "12-month term with automatic annual renewal. 60 days written cancellation notice required. Early termination fee: $75. Essential Plan (1 visit/year).",
        "default_services": [
            {"service_code": "SVC-VISIT", "description": "Annual service visit", "frequency": "annual", "quantity": 1},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "service_address", "system_type", "plan_tier"],
    },
    {
        "code": "EVERGREEN_SVC_2",
        "name": "Evergreen Service - 2 Visits",
        "description": "Evergreen service contract with 2 annual visits. Recommended for standard residential systems. Includes repair discounts.",
        "contract_type": "service",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "base_price": 295.00,
        "content": CONTRACT_4_SERVICE_VISITS,
        "terms_and_conditions": "12-month term with automatic annual renewal. 60 days written cancellation notice required. Early termination fee: $100. Standard Plan (2 visits/year).",
        "default_services": [
            {"service_code": "SVC-VISIT", "description": "Semi-annual service visit", "frequency": "semi-annual", "quantity": 2},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "service_address", "system_type", "plan_tier"],
    },
    {
        "code": "EVERGREEN_SVC_3",
        "name": "Evergreen Service - 3 Visits",
        "description": "Evergreen service contract with 3 annual visits. Best for commercial or high-usage systems. Maximum protection and discounts.",
        "contract_type": "service",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "base_price": 325.00,
        "content": CONTRACT_4_SERVICE_VISITS,
        "terms_and_conditions": "12-month term with automatic annual renewal. 60 days written cancellation notice required. Early termination fee: $125. Premium Plan (3 visits/year).",
        "default_services": [
            {"service_code": "SVC-VISIT", "description": "Tri-annual service visit", "frequency": "tri-annual", "quantity": 3},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "service_address", "system_type", "plan_tier"],
    },
    {
        "code": "COMMERCIAL_SMALL",
        "name": "Commercial - Small Business",
        "description": "Commercial septic maintenance for systems up to 1,500 gallons. Quarterly visits, TCEQ compliance, and emergency response.",
        "contract_type": "commercial",
        "default_duration_months": 24,
        "default_billing_frequency": "monthly",
        "default_payment_terms": "net-30",
        "default_auto_renew": True,
        "base_price": 850.00,
        "content": CONTRACT_5_COMMERCIAL,
        "terms_and_conditions": "24-month initial term with automatic 12-month renewal. 90 days written cancellation notice required. Early termination: 50% of remaining value (initial term); 3 months value (renewal terms). Small Business Tier.",
        "default_services": [
            {"service_code": "COMM-MAINT", "description": "Commercial maintenance visit", "frequency": "quarterly", "quantity": 4},
            {"service_code": "TCEQ-FILE", "description": "TCEQ compliance reporting", "frequency": "annual", "quantity": 1},
            {"service_code": "PERF-RPT", "description": "Quarterly performance report", "frequency": "quarterly", "quantity": 4},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "contact_person", "service_address", "system_type", "system_capacity", "commercial_tier"],
    },
    {
        "code": "COMMERCIAL_MEDIUM",
        "name": "Commercial - Medium",
        "description": "Commercial septic maintenance for 1,501-5,000 gallon systems. Bi-monthly visits, grease trap service, dedicated account manager.",
        "contract_type": "commercial",
        "default_duration_months": 24,
        "default_billing_frequency": "monthly",
        "default_payment_terms": "net-30",
        "default_auto_renew": True,
        "base_price": 1400.00,
        "content": CONTRACT_5_COMMERCIAL,
        "terms_and_conditions": "24-month initial term with automatic 12-month renewal. 90 days written cancellation notice required. Early termination: 50% of remaining value (initial term); 3 months value (renewal terms). Medium Commercial Tier.",
        "default_services": [
            {"service_code": "COMM-MAINT", "description": "Commercial maintenance visit", "frequency": "bi-monthly", "quantity": 6},
            {"service_code": "GREASE-TRAP", "description": "Grease trap cleaning", "frequency": "annual", "quantity": 1},
            {"service_code": "TCEQ-FILE", "description": "TCEQ compliance reporting", "frequency": "annual", "quantity": 1},
            {"service_code": "PERF-RPT", "description": "Semi-annual management report", "frequency": "semi-annual", "quantity": 2},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "contact_person", "service_address", "system_type", "system_capacity", "commercial_tier"],
    },
    {
        "code": "COMMERCIAL_LARGE",
        "name": "Commercial - Large",
        "description": "Full-service commercial maintenance for 5,001+ gallon systems. Monthly visits, 24/7 emergency, complimentary annual pumping.",
        "contract_type": "commercial",
        "default_duration_months": 24,
        "default_billing_frequency": "monthly",
        "default_payment_terms": "net-30",
        "default_auto_renew": True,
        "base_price": 2200.00,
        "content": CONTRACT_5_COMMERCIAL,
        "terms_and_conditions": "24-month initial term with automatic 12-month renewal. 90 days written cancellation notice required. Early termination: 50% of remaining value (initial term); 3 months value (renewal terms). Large Commercial Tier.",
        "default_services": [
            {"service_code": "COMM-MAINT", "description": "Monthly commercial maintenance visit", "frequency": "monthly", "quantity": 12},
            {"service_code": "GREASE-TRAP", "description": "Grease trap cleaning", "frequency": "quarterly", "quantity": 4},
            {"service_code": "PUMP-COMP", "description": "Complimentary annual pumping", "frequency": "annual", "quantity": 1},
            {"service_code": "TCEQ-FILE", "description": "TCEQ compliance reporting", "frequency": "annual", "quantity": 1},
            {"service_code": "PERF-RPT", "description": "Monthly performance dashboard", "frequency": "monthly", "quantity": 12},
            {"service_code": "OPT-REVIEW", "description": "Annual system optimization review", "frequency": "annual", "quantity": 1},
        ],
        "variables": ["contract_number", "start_date", "customer_name", "contact_person", "service_address", "system_type", "system_capacity", "commercial_tier"],
    },
]
