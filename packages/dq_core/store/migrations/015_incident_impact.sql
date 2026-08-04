-- Observability-Intelligence v1: downstream object impact snapshot per incident.
ALTER TABLE dq_incidents ADD COLUMN impacted_objects TEXT DEFAULT '[]';
