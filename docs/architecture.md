# How Avuno is built

![How Avuno is built](architecture.svg)

## The same flow, in more detail

```mermaid
flowchart TD
    A[Brand's request<br>email, chat message or PDF] --> B[Read<br>rules only, each detail linked to its line]
    B -->|company, budget or niche missing| H1{{Ask a person}}
    H1 --> B
    B --> C[Check the company and sender]
    CD[(Crustdata<br>Identify, Enrich, Person Search,<br>Company Search, Job Search, Web Fetch)] <--> C
    C -->|impersonation or hidden ad| X[Stop. Nothing is started]
    C -->|same company, same campaign| D1[One record, no second deal]
    C --> E[Rank creators on evidence<br>published tiebreak chain]
    E --> F[Sealed limits and one published rule<br>sets terms and price]
    F --> G[Contract with SHA-256 fingerprint]
    G --> R[Live re-check before signing]
    CD <--> R
    R -->|a fact changed or a source failed| H2{{Ask a person}}
    H2 --> S
    R --> S[Sign, hold funds, delivery, approval]
    S --> P[Payout and invoice]
    P --> Z[Finished: contract, invoice, full record]

    subgraph State [SQLite: saved after every step]
      L[(Ledger with stable keys:<br>each email or payment happens once)]
      EV[(Append-only event log)]
    end
    F -.-> EV
    G -.-> L
    S -.-> L
    P -.-> L

    subgraph Mock [Simulated and labelled]
      O[Mock outbox]
      M[Signatures, escrow, payments]
    end
    L -.-> O
    L -.-> M
```

**After a crash,** each stage resumes from its last saved state. Actions already in the ledger are skipped, so nothing is sent or paid twice.

**Who decides:** code does. An LLM is optional, can only fill parsing gaps or polish a message, and never sets a price or a verdict.
