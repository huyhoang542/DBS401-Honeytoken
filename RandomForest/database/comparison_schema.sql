-- Experiment schema isolated for Demo B.
-- Does not read or alter Demo A's database.
CREATE DATABASE IF NOT EXISTS honeytoken_security_b;
USE honeytoken_security_b;

CREATE TABLE IF NOT EXISTS experiment_runs (
    run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    demo_version ENUM('A_STATIC', 'B_ADAPTIVE') NOT NULL,
    run_name VARCHAR(120) NOT NULL,
    dataset_version VARCHAR(120) NOT NULL,
    honeytoken_budget SMALLINT UNSIGNED NOT NULL,
    scenario_set VARCHAR(120) NOT NULL,
    random_seed INT NULL,
    model_name VARCHAR(120) NULL,
    model_config JSON NULL,
    started_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at DATETIME(6) NULL,
    notes TEXT NULL,
    PRIMARY KEY (run_id),
    KEY idx_experiment_runs_version_started (demo_version, started_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS experiment_query_results (
    result_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id BIGINT UNSIGNED NOT NULL,
    scenario_id VARCHAR(120) NOT NULL,
    query_type VARCHAR(40) NOT NULL,
    target_table VARCHAR(80) NOT NULL,
    requested_rows INT UNSIGNED NULL,
    returned_rows INT UNSIGNED NOT NULL DEFAULT 0,
    actual_label TINYINT UNSIGNED NOT NULL,
    predicted_label TINYINT UNSIGNED NOT NULL,
    risk_score DECIMAL(7,6) NULL,
    latency_ms DECIMAL(12,4) NOT NULL,
    detected_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    metadata JSON NULL,
    PRIMARY KEY (result_id),
    UNIQUE KEY uq_run_scenario (run_id, scenario_id),
    KEY idx_query_results_labels (run_id, actual_label, predicted_label),
    CONSTRAINT fk_query_results_run FOREIGN KEY (run_id)
        REFERENCES experiment_runs (run_id) ON DELETE CASCADE,
    CONSTRAINT chk_actual_binary CHECK (actual_label IN (0, 1)),
    CONSTRAINT chk_predicted_binary CHECK (predicted_label IN (0, 1)),
    CONSTRAINT chk_latency_nonnegative CHECK (latency_ms >= 0),
    CONSTRAINT chk_risk_score CHECK (risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 1))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS placement_update_history (
    placement_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id BIGINT UNSIGNED NULL,
    token_emp_no INT NOT NULL,
    from_department CHAR(4) NOT NULL,
    to_department CHAR(4) NOT NULL,
    placement_strategy VARCHAR(40) NOT NULL,
    update_cost_ms DECIMAL(12,4) NULL,
    changed_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (placement_id),
    KEY idx_placement_run (run_id),
    KEY idx_placement_changed (changed_at),
    CONSTRAINT fk_placement_run FOREIGN KEY (run_id)
        REFERENCES experiment_runs (run_id) ON DELETE SET NULL
) ENGINE=InnoDB;
