-- Operational security tables for a clean, isolated Demo B installation.
-- Safe to re-run: CREATE IF NOT EXISTS does not erase existing event data.
CREATE DATABASE IF NOT EXISTS honeytoken_security_b;

CREATE TABLE IF NOT EXISTS honeytoken_security_b.honeytoken_registry (
    token_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    emp_no INT NOT NULL,
    placement_strategy VARCHAR(40) NOT NULL DEFAULT 'STATIC',
    placement_version VARCHAR(80) NOT NULL DEFAULT 'baseline_v1',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (token_id),
    UNIQUE KEY uq_honeytoken_emp_no (emp_no),
    KEY idx_honeytoken_active (is_active)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS honeytoken_security_b.access_events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(128) NOT NULL,
    query_type VARCHAR(40) NOT NULL,
    target_table VARCHAR(80) NOT NULL,
    query_text TEXT NOT NULL,
    returned_rows INT UNSIGNED NOT NULL DEFAULT 0,
    honeytoken_hit BOOLEAN NOT NULL DEFAULT FALSE,
    event_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id),
    KEY idx_access_events_time (event_time),
    KEY idx_access_events_hit (honeytoken_hit)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS honeytoken_security_b.security_alerts (
    alert_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_id BIGINT UNSIGNED NOT NULL,
    token_id BIGINT UNSIGNED NOT NULL,
    severity VARCHAR(16) NOT NULL,
    message VARCHAR(500) NOT NULL,
    alert_time DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (alert_id),
    KEY idx_security_alert_event (event_id),
    KEY idx_security_alert_token (token_id),
    CONSTRAINT fk_security_alert_event FOREIGN KEY (event_id)
        REFERENCES honeytoken_security_b.access_events (event_id),
    CONSTRAINT fk_security_alert_token FOREIGN KEY (token_id)
        REFERENCES honeytoken_security_b.honeytoken_registry (token_id)
) ENGINE=InnoDB;
