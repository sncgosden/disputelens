# Claim rating packet (mastercard-fresh-v1)

For each claim, rate whether it applies to the situation in the question: yes, no, or unsure.
A claim applies if a merchant in exactly that situation could rely on it. Rate "no" if it only holds for a different
reason code, region, card scheme, program or subtype than the question describes.

## F01

**Question:** A customer who bought a vacation-ownership package from my resort says they want out of the contract. What does the Mastercard guide say about how the issuer can dispute it?

**Claim 1:** The only timeshare-specific dispute language in the pack is in the Single Message System arbitration case filing section, for a 75-Refund Not Received case. The cardholder's statement there can say the account has not been credited for a canceled timeshare agreement, with the cancellation made within the applicable time frame.

- Cited section: Chapter 5 Pre-Arbitration and Arbitration Case Filing > Time Frames and Requirements > Single Message System Arbitration Case Filing
  - Quote: "For cases involving 75-Refund Not Received the following must also be included:"
- Cited section: Chapter 5 Pre-Arbitration and Arbitration Case Filing > Time Frames and Requirements > Single Message System Arbitration Case Filing
  - Quote: "account has not been credited for a canceled timeshare agreement and the cancellation occurred within the applicable time frame"

Rating F01-1: ______

## F02

**Question:** A customer's card was charged twice for one delivery, two identical charges a minute apart. What does Mastercard's guide say the issuer has to show?

**Claim 1:** Dual Message System, reason code 4834 (Cardholder Debited More than Once for the Same Goods or Services): the issuer may charge back when the cardholder contacted the issuer and the claim is sufficiently detailed in the supporting documentation, where required. The condition listed is that the cardholder's account was debited more than once for the same transaction.

- Cited section: Chapter 2 Dual Message System Chargebacks > Point-of-Interaction Error (Message Reason Code 4834/34) > Cardholder Debited More than Once for the Same Goods or Services > Issuer Chargeback
  - Quote: "The cardholder’s account has been debited more than once for the same transaction."

Rating F02-1: ______

**Claim 2:** For duplicate Maestro transactions where the card was issued in Europe or the terminal was in Europe (not both), the POS terminal transaction amount and the date and time must be the same for the transactions in question.

- Cited section: Chapter 2 Dual Message System Chargebacks > Point-of-Interaction Error (Message Reason Code 4834/34) > Cardholder Debited More than Once for the Same Goods or Services > Issuer Chargeback
  - Quote: "The POS terminal transaction amount and the date and time of the transaction must be the same for the transactions in question."

Rating F02-2: ______

**Claim 3:** Single Message System, reason code 73 (Duplicate Transaction): the issuer can determine a duplicate when the terminal number, amount, date and authorization response code are identical across the transactions in question.

- Cited section: Chapter 3 Single Message System Chargebacks > Chargeback Reason Codes > Duplicate Transaction > Issuer Chargeback
  - Quote: "ATM or POS terminal number, transaction amount, transaction date, and authorization response code are identical for the transactions in question."

Rating F02-3: ______

**Claim 4:** Under Single Message System reason code 73, the guide lists no supporting documents for the chargeback.

- Cited section: Chapter 3 Single Message System Chargebacks > Chargeback Reason Codes > Duplicate Transaction > Issuer Chargeback
  - Quote: "Supporting Documents None"

Rating F02-4: ______

## F03

**Question:** A cardholder says the cash machine at my kiosk gave out no cash but their account was debited. What must the issuer provide to charge it back?

**Claim 1:** In the Dual Message System, the Point-of-Interaction Error chargeback (4834/34) may be used when the cardholder contacts the issuer and alleges that cash was not properly dispensed by an ATM.

- Cited section: Chapter 2 Dual Message System Chargebacks > Point-of-Interaction Error (Message Reason Code 4834/34)
  - Quote: "Cash was not properly dispensed by an ATM."

Rating F03-1: ______

## F04

**Question:** I run a subscription box. A customer says they cancelled before the renewal and I charged them anyway. How does the guide treat that kind of dispute?

**Claim 1:** The guide covers this under Cardholder Dispute chargebacks (4853) in a section on a recurring transaction that was cancelled, or that the cardholder did not know was recurring. A recurring transaction is continuous billing without a specified end date, and the disputed transaction must be recurring, not installment billing.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Cardholder Dispute of a Recurring Transaction
  - Quote: "This section details the conditions for addressing a cardholder claim that a recurring transaction was either cancelled or the cardholder was not aware they were agreeing to a recurring transaction."
- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Cardholder Dispute of a Recurring Transaction
  - Quote: "The disputed transaction must be a recurring transaction and not installment billing."

Rating F04-1: ______

**Claim 2:** The issuer may charge back when the cardholder says they notified the merchant to cancel and the merchant kept billing. The issuer may also charge back when the cardholder says they were not aware they were agreeing to a recurring transaction.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Cardholder Dispute of a Recurring Transaction > Issuer Chargeback
  - Quote: "The cardholder notified the merchant to cancel the recurring transaction and the merchant continued to bill the cardholder."
- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Cardholder Dispute of a Recurring Transaction > Issuer Chargeback
  - Quote: "The cardholder was not aware that the cardholder was agreeing to a recurring transaction."

Rating F04-2: ______

**Claim 3:** The issuer's supporting documentation must be a cardholder letter, email, message or Form 1221. For a cancellation claim it must specify that the cardholder notified the merchant to cancel, and the date of the notification.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Cardholder Dispute of a Recurring Transaction > Issuer Chargeback
  - Quote: "The cardholder notified the merchant to cancel the recurring transaction and the date of the notification."

Rating F04-3: ______

**Claim 4:** The guide also lists other issuer grounds for a recurring-transaction dispute (other than Mainland China domestic): the issuer listed the account in the Payment Cancellation Service, previously charged back a disputed recurring transaction with the same PAN and merchant, or previously notified the merchant or acquirer to cancel before the disputed transaction. If the issuer continues after your second presentment, the cardholder reasserting the cancellation claim is one pre-arbitration ground.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Issuer Dispute of a Recurring Transaction > Issuer Chargeback
  - Quote: "The issuer listed the account in the Payment Cancellation Service (PCS) prior to the disputed transaction occurring."
- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Cardholder Dispute of a Recurring Transaction > Issuer Submission of a Pre-arbitration Case
  - Quote: "The cardholder reasserts their claim that the recurring transaction was either cancelled or the cardholder was not aware they were agreeing to a recurring transaction."

Rating F04-4: ______

## F05

**Question:** A cardholder says the designer bag I sold was a fake. What does the guide require for that kind of dispute?

**Claim 1:** For the general Dual Message System counterfeit-goods chargeback, the supporting documentation must include a reasonably specific description of the goods purchased. It should also say what happened to the goods, for example held by customs, held by the cardholder, discarded, or returned to the merchant.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Counterfeit Goods > Issuer Chargeback
  - Quote: "A reasonably specific description of the goods/services purchased."
- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Counterfeit Goods > Issuer Chargeback
  - Quote: "The cardholder returned the goods to the merchant."

Rating F05-1: ______

**Claim 2:** The cardholder's email, letter or message must come directly from the cardholder (or the corporate entity for a commercial card). A completed dispute form must be the direct result of a conversation with the cardholder.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Counterfeit Goods > Issuer Chargeback
  - Quote: "must come directly from the cardholder or, in the case of a commercial card, the corporate entity."

Rating F05-2: ______

**Claim 3:** The time frame is generally 120 calendar days from the Settlement Date or Central Site Business Date. For Mainland China domestic transactions it is 90 calendar days from the settlement date. Delayed-delivery variations also exist.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Counterfeit Goods > Issuer Chargeback
  - Quote: "Within 120-calendar days of the Settlement Date or Central Site Business Date."
- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Counterfeit Goods > Issuer Chargeback
  - Quote: "Within 90-calendar days of transaction settlement date."

Rating F05-3: ______

**Claim 4:** If the dispute escalates to pre-arbitration, the issuer's documentation can include evidence from a bona fide expert that the goods are counterfeit. It can alternatively show the merchant was closed by a governmental agency for selling counterfeit goods.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Counterfeit Goods > Issuer Submission of a Pre-arbitration Case
  - Quote: "Documentation from a bona fide expert substantiating that the disputed goods are counterfeit"
- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Counterfeit Goods > Issuer Submission of a Pre-arbitration Case
  - Quote: "was closed by a governmental agency for selling counterfeit goods"

Rating F05-4: ______

## F06

**Question:** A customer was billed for damage to a rental car after returning it. What does the guide say about disputing charges for damage?

**Claim 1:** Where the cardholder was billed for damage in the same transaction as the underlying initial service, the issuer may charge it back under Point-of-Interaction Error (reason code 4834), provided the cardholder contacted the issuer and the claim is sufficiently detailed in the supporting documentation.

- Cited section: Chapter 2 Dual Message System Chargebacks > Point-of-Interaction Error (Message Reason Code 4834/34) > Charges for Loss, Theft, or Damages > Issuer Chargeback
  - Quote: "billed for loss, theft, or damage in the same transaction as the underlying initial service"

Rating F06-1: ______

**Claim 2:** Where the damage charge was processed as a separate (addendum) transaction, the guide directs the issuer to the Cardholder Dispute chargeback (reason code 4853) instead.

- Cited section: Chapter 2 Dual Message System Chargebacks > Point-of-Interaction Error (Message Reason Code 4834/34) > Charges for Loss, Theft, or Damages > Issuer Chargeback
  - Quote: "should be used to dispute a charge for loss, theft, or damage processed as a separate (addendum) transaction."

Rating F06-2: ______

**Claim 3:** The guide says a cardholder is not responsible for a damage charge unless the transaction was completed as described in Transaction Processing Rules section 3.12, which applies to Mastercard POS transactions only.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Addendum Dispute > Issuer Chargeback
  - Quote: "A cardholder is not responsible for a charge representing loss, theft, or damage unless the transaction was completed as described in the Transaction Processing Rules"

Rating F06-3: ______

**Claim 4:** For an addendum dispute over damage charges, the acquirer's second presentment must include documentation substantiating that the transaction was completed as described in section 3.12. The guide gives the original rental agreement as an example.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Addendum Dispute > Acquirer Second Presentment > Valid addendum transaction
  - Quote: "When the disputed amount presents charges for loss, theft, or damage: Documentation substantiating the transaction was completed as described"
- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Addendum Dispute > Acquirer Second Presentment > Valid addendum transaction
  - Quote: "The original rental agreement or hotel folio."

Rating F06-4: ______

## F07

**Question:** A customer disputes a charge from three months ago. Is a chargeback still allowed, and what time limits apply?

## F08

**Question:** What documents can the issuer send with a chargeback, and what must they contain?

**Claim 1:** Supporting documentation is evidence, typically from the cardholder or merchant, that the issuer attaches to the chargeback. The permitted documents and their required contents vary by dispute type, so a single general list cannot be given.

- Cited section: Chapter 2 Dual Message System Chargebacks > Fraud-related Chargebacks (Message Reason Codes 4837/37/4870/70/4871/4849/49) > Chip Liability Shift-Lost/Stolen/Never Received Issue (NRI) Fraud (Message Reason Code 4871) > Supporting Documentation
  - Quote: "Supporting documentation requirements vary by dispute type and are described in their corresponding sections."
- Cited section: Chapter 2 Dual Message System Chargebacks > Fraud-related Chargebacks (Message Reason Codes 4837/37/4870/70/4871/4849/49) > Chip Liability Shift-Lost/Stolen/Never Received Issue (NRI) Fraud (Message Reason Code 4871) > Supporting Documentation
  - Quote: "documentation typically provided by the cardholder or merchant and attached by the issuer or acquirer to the dispute as evidence in support of the chargeback"

Rating F08-1: ______

## F09

**Question:** We resubmitted the transaction after the cardholder complained. Can the issuer still charge it back?

## F10

**Question:** My acquirer says the issuer filed a pre-arbitration case against me. What happens next and what can I expect?

**Claim 1:** After a pre-arbitration filing, the acquirer (not the merchant directly) chooses a response. One option is to accept the case, which means taking financial responsibility for the disputed transaction.

- Cited section: Chapter 2 Dual Message System Chargebacks > Authorization-related Chargeback (Message Reason Code 4808/08) > Required Authorization Not Obtained > Acquirer Response to a Pre-arbitration Case
  - Quote: "Accept the pre-arbitration case and thereby financial responsibility for the disputed transaction."

Rating F10-1: ______

**Claim 2:** If the acquirer takes no action, Mastercom automatically accepts the case on the acquirer's behalf after 30 calendar days, which also means financial responsibility for the transaction.

- Cited section: Chapter 2 Dual Message System Chargebacks > Authorization-related Chargeback (Message Reason Code 4808/08) > Required Authorization Not Obtained > Acquirer Response to a Pre-arbitration Case
  - Quote: "Take no action and thereby accept financial responsibility for the disputed transaction."
- Cited section: Chapter 2 Dual Message System Chargebacks > Authorization-related Chargeback (Message Reason Code 4808/08) > Required Authorization Not Obtained > Acquirer Response to a Pre-arbitration Case
  - Quote: "The Mastercom application will automatically accept the pre-arbitration case on behalf of the acquirer after 30-calendar days from the Submit Date specified within the Mastercom application."

Rating F10-2: ______

**Claim 3:** The acquirer can instead reject the pre-arbitration case with a rebuttal and any relevant documentation.

- Cited section: Chapter 2 Dual Message System Chargebacks > Authorization-related Chargeback (Message Reason Code 4808/08) > Required Authorization Not Obtained > Acquirer Response to a Pre-arbitration Case
  - Quote: "Reject the pre-arbitration case with a rebuttal and any relevant documentation."

Rating F10-3: ______

**Claim 4:** If the issuer files an arbitration case before the 30 calendar days have passed, the acquirer's response options move from the pre-arbitration step to the arbitration step. The guide says the available actions are the same across chargebacks.

- Cited section: Chapter 2 Dual Message System Chargebacks > Authorization-related Chargeback (Message Reason Code 4808/08) > Transit First Ride Risk (FRR) Claims > Acquirer Response to a Pre-arbitration Case
  - Quote: "if the issuer files an arbitration case before the 30-calendar days have passed, these options are no longer available within the pre-arbitration step"
- Cited section: Chapter 2 Dual Message System Chargebacks > Authorization-related Chargeback (Message Reason Code 4808/08) > Required Authorization Not Obtained > Acquirer Response to a Pre-arbitration Case
  - Quote: "The actions available to an acquirer in response to a pre-arbitration case are the same across chargebacks."

Rating F10-4: ______

## F11

**Question:** What happens when the issuer disagrees with my response to a chargeback? Can they escalate?

**Claim 1:** Yes, in the cardholder dispute "Transaction Did Not Complete" section, the issuer may escalate a rejected pre-arbitration case to an arbitration case. This applies if the issuer still believes the chargeback is valid and the acquirer failed to remedy the pre-arbitration case.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Transaction Did Not Complete > Acquirer Response to an Arbitration Case
  - Quote: "when the issuer continues to believe the chargeback is valid"
- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Transaction Did Not Complete > Acquirer Response to an Arbitration Case
  - Quote: "and the acquirer failed to remedy the pre-arbitration case."

Rating F11-1: ______

**Claim 2:** Once an arbitration case is filed, the acquirer may accept it and take financial responsibility for the disputed transaction at any time before Mastercard rules on the case.

- Cited section: Chapter 2 Dual Message System Chargebacks > Cardholder Dispute Chargeback (Message Reason Code 4853/53/4850/4854) > Transaction Did Not Complete > Acquirer Response to an Arbitration Case
  - Quote: "An acquirer may accept the arbitration case and thereby financial responsibility for the disputed transaction at any time before Mastercard rules on the case."

Rating F11-2: ______

## F12

**Question:** A customer says the amount on the receipt was different from what they were charged. What are the options for the issuer?

**Claim 1:** For a Mastercard dispute where the cardholder says they were billed an incorrect amount, the issuer's option shown in the pack is a Point-of-Interaction Error (4834/34) chargeback under "Transaction Amount Differs". The cardholder must have contacted the issuer with this claim, and it must be sufficiently detailed in the supporting documentation when required.

- Cited section: Chapter 2 Dual Message System Chargebacks > Point-of-Interaction Error (Message Reason Code 4834/34) > Transaction Amount Differs > Issuer Chargeback
  - Quote: "The issuer may chargeback a transaction when the cardholder contacted the issuer claiming the cardholder was billed an incorrect amount"

Rating F12-1: ______

**Claim 2:** If the disputed difference involves a gratuity amount, the supporting documents are a cardholder letter, email, message or Form 1240. It must describe the complaint and state the transaction amount that should have been billed.

- Cited section: Chapter 2 Dual Message System Chargebacks > Point-of-Interaction Error (Message Reason Code 4834/34) > Transaction Amount Differs > Issuer Chargeback
  - Quote: "including the transaction amount that should have been billed."

Rating F12-2: ______

**Claim 3:** If the difference arises from currency handling, a separate Currency Errors chargeback (4834/34) is available. One of its conditions is that currency conversion was performed incorrectly and an incorrect amount was deducted from the cardholder's account.

- Cited section: Chapter 2 Dual Message System Chargebacks > Point-of-Interaction Error (Message Reason Code 4834/34) > Currency Errors > Issuer Chargeback
  - Quote: "Currency conversion was performed incorrectly resulting in an incorrect amount being deducted"

Rating F12-3: ______
