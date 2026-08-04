-- ADR-0001: artifact kind discriminator (internal_gate | consumer_contract | provider_contract).
-- Default to internal_gate: existing contracts created before kind-awareness are DQ-First gates.
ALTER TABLE dq_check_results ADD COLUMN kind TEXT NOT NULL DEFAULT 'internal_gate';
