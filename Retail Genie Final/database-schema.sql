-- Retail Genie initial MySQL schema
-- Target: MySQL 8.x with InnoDB. Generated from the application SQLAlchemy models.
-- Intended only for a new, empty retail_genie database.
-- Do not run against an existing installation or database containing business data.

USE retail_genie;


CREATE TABLE tenant_containers (
	id VARCHAR(64) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	slug VARCHAR(64) NOT NULL, 
	timezone VARCHAR(64) NOT NULL, 
	is_active BOOL NOT NULL, 
	policy_version INTEGER NOT NULL DEFAULT '1', 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_tenant_containers_slug UNIQUE (slug)
)ENGINE=InnoDB CHARSET=utf8mb4;


CREATE TABLE subscription_plans (
	id VARCHAR(64) NOT NULL, 
	code VARCHAR(40) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description VARCHAR(500), 
	monthly_price NUMERIC(12, 3) NOT NULL, 
	max_companies INTEGER, 
	max_stores INTEGER, 
	max_active_users INTEGER, 
	features JSON NOT NULL, 
	is_active BOOL NOT NULL, 
	sort_order INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_subscription_plans_nonnegative_price CHECK (monthly_price >= 0), 
	CONSTRAINT ck_subscription_plans_company_limit CHECK (max_companies IS NULL OR max_companies >= 1), 
	CONSTRAINT ck_subscription_plans_store_limit CHECK (max_stores IS NULL OR max_stores >= 1), 
	CONSTRAINT ck_subscription_plans_user_limit CHECK (max_active_users IS NULL OR max_active_users >= 1), 
	CONSTRAINT uq_subscription_plans_code UNIQUE (code)
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_subscription_plans_active_sort ON subscription_plans (is_active, sort_order);


CREATE TABLE companies (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	parent_company_id VARCHAR(64), 
	name VARCHAR(160) NOT NULL, 
	slug VARCHAR(64) NOT NULL, 
	timezone VARCHAR(64) NOT NULL, 
	mixed_tender_category VARCHAR(24) NOT NULL DEFAULT 'other', 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_companies_mixed_tender_category CHECK (mixed_tender_category IN ('cash', 'bank', 'bank_transfer', 'other')), 
	CONSTRAINT fk_companies_parent_same_container FOREIGN KEY(tenant_container_id, parent_company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_companies_container_id_id UNIQUE (tenant_container_id, id), 
	CONSTRAINT uq_companies_container_slug UNIQUE (tenant_container_id, slug), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_companies_tenant_container_id ON companies (tenant_container_id);


CREATE TABLE stores (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	code VARCHAR(48) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_stores_company_same_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_stores_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT uq_stores_container_id_id UNIQUE (tenant_container_id, id), 
	CONSTRAINT uq_stores_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_stores_container_company_code UNIQUE (tenant_container_id, company_id, code), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_stores_container_company_active ON stores (tenant_container_id, company_id, is_active);

CREATE INDEX ix_stores_tenant_container_id ON stores (tenant_container_id);


CREATE TABLE users (
	id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	username VARCHAR(48) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	`role` VARCHAR(24) NOT NULL, 
	permissions JSON NOT NULL, 
	is_active BOOL NOT NULL, 
	force_password_change BOOL NOT NULL, 
	auth_version INTEGER NOT NULL, 
	active_break_id VARCHAR(64), 
	auto_enter_after_scan BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_users_valid_role CHECK (role IN ('super_admin', 'company_admin', 'admin', 'manager', 'salesperson', 'storekeeper', 'cashier', 'logistics', 'auditor', 'display', 'express')), 
	CONSTRAINT uq_users_company_id_id UNIQUE (company_id, id), 
	FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_users_company_id ON users (company_id);

CREATE UNIQUE INDEX ix_users_username ON users (username);


CREATE TABLE billing_series (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	category VARCHAR(24) NOT NULL, 
	prefix VARCHAR(24) NOT NULL, 
	next_number INTEGER NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_billing_series_category CHECK (category IN ('cash', 'bank', 'bank_transfer', 'other')), 
	CONSTRAINT ck_billing_series_positive_next CHECK (next_number > 0), 
	CONSTRAINT ck_billing_series_nonempty_prefix CHECK (length(trim(prefix)) > 0), 
	CONSTRAINT fk_billing_series_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_billing_series_company_category UNIQUE (company_id, category), 
	CONSTRAINT uq_billing_series_company_prefix UNIQUE (company_id, prefix), 
	CONSTRAINT uq_billing_series_company_id_id UNIQUE (company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_billing_series_container_company ON billing_series (tenant_container_id, company_id);


CREATE TABLE order_number_series (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	prefix VARCHAR(24) NOT NULL, 
	next_number INTEGER NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_number_series_positive_next CHECK (next_number > 0), 
	CONSTRAINT ck_order_number_series_nonempty_prefix CHECK (length(trim(prefix)) > 0), 
	CONSTRAINT fk_order_number_series_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_order_number_series_company UNIQUE (company_id), 
	CONSTRAINT uq_order_number_series_company_prefix UNIQUE (company_id, prefix), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_order_number_series_container_company ON order_number_series (tenant_container_id, company_id);


CREATE TABLE business_number_series (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	document_type VARCHAR(24) NOT NULL, 
	prefix VARCHAR(24) NOT NULL, 
	next_number INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_business_number_series_type CHECK (document_type IN ('demand_notice', 'quotation', 'purchase_order', 'store_credit')), 
	CONSTRAINT ck_business_number_series_next_positive CHECK (next_number > 0), 
	CONSTRAINT ck_business_number_series_prefix_nonempty CHECK (length(trim(prefix)) > 0), 
	CONSTRAINT fk_business_number_series_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_business_number_series_company_type UNIQUE (company_id, document_type), 
	CONSTRAINT uq_business_number_series_company_prefix UNIQUE (company_id, prefix), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_business_number_series_container_company ON business_number_series (tenant_container_id, company_id);


CREATE TABLE hr_attendance_logs (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(64) NOT NULL, 
	attendance_date VARCHAR(10) NOT NULL, 
	timestamp DATETIME NOT NULL, 
	method VARCHAR(16) NOT NULL, 
	selfie_data_uri TEXT, 
	selfie_image_path TEXT, 
	clock_out_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_attendance_logs_method CHECK (method IN ('auto', 'manual', 'selfie')), 
	CONSTRAINT ck_attendance_logs_clockout_order CHECK (clock_out_at IS NULL OR clock_out_at > timestamp), 
	CONSTRAINT fk_attendance_logs_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_attendance_logs_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_attendance_logs_company_user_day UNIQUE (tenant_container_id, company_id, user_id, attendance_date), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_attendance_logs_container_company_date ON hr_attendance_logs (tenant_container_id, company_id, attendance_date);


CREATE TABLE hr_break_logs (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(64) NOT NULL, 
	start_time DATETIME NOT NULL, 
	end_time DATETIME, 
	duration_ms INTEGER, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_break_logs_duration_nonnegative CHECK (duration_ms IS NULL OR duration_ms >= 0), 
	CONSTRAINT ck_break_logs_end_order CHECK (end_time IS NULL OR end_time >= start_time), 
	CONSTRAINT fk_break_logs_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_break_logs_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_break_logs_container_user_start ON hr_break_logs (tenant_container_id, user_id, start_time);


CREATE TABLE container_memberships (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	`role` VARCHAR(24) NOT NULL, 
	permissions JSON NOT NULL, 
	is_default BOOL NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_container_memberships_valid_role CHECK (role IN ('super_admin', 'company_admin', 'admin', 'manager', 'salesperson', 'storekeeper', 'cashier', 'logistics', 'auditor', 'display', 'express')), 
	CONSTRAINT fk_container_memberships_company FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_container_memberships_container_user UNIQUE (tenant_container_id, user_id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_container_memberships_user_active ON container_memberships (user_id, is_active);


CREATE TABLE tenant_data_policies (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	domain VARCHAR(32) NOT NULL, 
	sharing_mode VARCHAR(24) NOT NULL, 
	is_enabled BOOL NOT NULL, 
	policy_version INTEGER NOT NULL, 
	changed_by_user_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_tenant_data_policies_sharing_mode CHECK (sharing_mode IN ('container', 'company', 'assigned_store', 'selected_units', 'disabled')), 
	CONSTRAINT ck_tenant_data_policies_domain CHECK (domain IN ('product_catalog', 'inventory', 'customers', 'open_bills', 'sales', 'staff_accounts', 'suppliers', 'reports', 'files', 'audit', 'cashups', 'settings')), 
	CONSTRAINT uq_tenant_data_policies_container_domain UNIQUE (tenant_container_id, domain), 
	CONSTRAINT uq_tenant_data_policies_container_id_id UNIQUE (tenant_container_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(changed_by_user_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_tenant_data_policies_container_enabled ON tenant_data_policies (tenant_container_id, is_enabled);


CREATE TABLE audit_events (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	store_id VARCHAR(64), 
	actor_user_id VARCHAR(64), 
	action VARCHAR(64) NOT NULL, 
	entity_type VARCHAR(64) NOT NULL, 
	entity_id VARCHAR(64) NOT NULL, 
	reason VARCHAR(500), 
	before_data JSON, 
	after_data JSON, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_audit_events_company_scope FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_audit_events_store_scope FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE RESTRICT, 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_audit_events_entity ON audit_events (entity_type, entity_id);

CREATE INDEX ix_audit_events_container_store_created ON audit_events (tenant_container_id, store_id, created_at);

CREATE INDEX ix_audit_events_container_created ON audit_events (tenant_container_id, created_at);


CREATE TABLE backup_settings (
	id SMALLINT NOT NULL, 
	enabled BOOL NOT NULL, 
	interval_minutes SMALLINT NOT NULL, 
	retention_count SMALLINT NOT NULL, 
	next_run_at DATETIME, 
	updated_by_id VARCHAR(64), 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_backup_settings_singleton CHECK (id = 1), 
	CONSTRAINT ck_backup_settings_interval CHECK (interval_minutes BETWEEN 15 AND 10080), 
	CONSTRAINT ck_backup_settings_retention CHECK (retention_count BETWEEN 1 AND 365), 
	FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;


CREATE TABLE backup_runs (
	id VARCHAR(36) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	trigger_type VARCHAR(16) NOT NULL, 
	requested_by_id VARCHAR(64), 
	requested_at DATETIME NOT NULL, 
	started_at DATETIME, 
	finished_at DATETIME, 
	file_name VARCHAR(180), 
	file_size_bytes BIGINT, 
	sha256 VARCHAR(64), 
	file_retained BOOL NOT NULL, 
	error_message TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_backup_runs_status CHECK (status IN ('queued', 'running', 'succeeded', 'failed')), 
	CONSTRAINT ck_backup_runs_trigger_type CHECK (trigger_type IN ('manual', 'scheduled')), 
	FOREIGN KEY(requested_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_backup_runs_status_requested_at ON backup_runs (status, requested_at);

CREATE INDEX ix_backup_runs_finished_at ON backup_runs (finished_at);


CREATE TABLE catalog_products (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	sku VARCHAR(128), 
	barcode VARCHAR(128), 
	name TEXT NOT NULL, 
	category VARCHAR(128), 
	price NUMERIC(14, 3), 
	low_stock_price NUMERIC(14, 3), 
	expiry_date DATETIME, 
	is_demand_notice_product BOOL NOT NULL, 
	image_url TEXT, 
	is_active BOOL NOT NULL, 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_catalog_products_price_nonnegative CHECK (price IS NULL OR price >= 0), 
	CONSTRAINT ck_catalog_products_low_stock_price_nonnegative CHECK (low_stock_price IS NULL OR low_stock_price >= 0), 
	CONSTRAINT ck_catalog_products_active_bool CHECK (is_active IN (0, 1)), 
	CONSTRAINT ck_catalog_products_demand_notice_bool CHECK (is_demand_notice_product IN (0, 1)), 
	CONSTRAINT fk_catalog_products_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_catalog_products_tenant_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_catalog_products_container_company_sku ON catalog_products (tenant_container_id, company_id, sku);

CREATE INDEX ix_catalog_products_container_barcode ON catalog_products (tenant_container_id, barcode);

CREATE INDEX ix_catalog_products_container_company_active ON catalog_products (tenant_container_id, company_id, is_active);


CREATE TABLE daily_cashups (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	business_date DATE NOT NULL, 
	submitted_by_id VARCHAR(64) NOT NULL, 
	expected_cash NUMERIC(14, 3) NOT NULL, 
	expected_bank NUMERIC(14, 3) NOT NULL, 
	expected_bank_transfer NUMERIC(14, 3) NOT NULL, 
	expected_other NUMERIC(14, 3) NOT NULL, 
	counted_cash NUMERIC(14, 3) NOT NULL, 
	counted_bank NUMERIC(14, 3) NOT NULL, 
	counted_bank_transfer NUMERIC(14, 3) NOT NULL, 
	counted_other NUMERIC(14, 3) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	notes TEXT, 
	reviewed_by_id VARCHAR(64), 
	review_note VARCHAR(500), 
	submitted_at DATETIME NOT NULL, 
	reviewed_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_daily_cashups_status CHECK (status IN ('submitted', 'approved', 'rejected')), 
	CONSTRAINT ck_daily_cashups_counted_amounts_nonnegative CHECK (counted_cash >= 0 AND counted_bank >= 0 AND counted_bank_transfer >= 0 AND counted_other >= 0), 
	CONSTRAINT fk_daily_cashups_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_daily_cashups_store_container FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_daily_cashups_store_day UNIQUE (company_id, store_id, business_date), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(submitted_by_id) REFERENCES users (id) ON DELETE RESTRICT, 
	FOREIGN KEY(reviewed_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_daily_cashups_company_date_status ON daily_cashups (tenant_container_id, company_id, business_date, status);


CREATE TABLE commercial_quotations (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	quotation_number VARCHAR(64) NOT NULL, 
	salesperson_id VARCHAR(64), 
	customer_name VARCHAR(160), 
	customer_phone VARCHAR(64) NOT NULL, 
	customer_email VARCHAR(254), 
	customer_address TEXT, 
	preparation_days INTEGER NOT NULL, 
	valid_until DATE, 
	status VARCHAR(24) NOT NULL, 
	total_amount NUMERIC(14, 3) NOT NULL, 
	notes TEXT, 
	created_by_id VARCHAR(64), 
	updated_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_commercial_quotations_status CHECK (status IN ('draft', 'sent', 'accepted', 'rejected', 'cancelled', 'expired', 'converted')), 
	CONSTRAINT ck_commercial_quotations_preparation_nonnegative CHECK (preparation_days >= 0), 
	CONSTRAINT ck_commercial_quotations_total_nonnegative CHECK (total_amount >= 0), 
	CONSTRAINT fk_commercial_quotations_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_commercial_quotations_store_container FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_commercial_quotations_company_number UNIQUE (company_id, quotation_number), 
	CONSTRAINT uq_commercial_quotations_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(salesperson_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_commercial_quotations_store_status_created ON commercial_quotations (tenant_container_id, company_id, store_id, status, created_at);

CREATE INDEX ix_commercial_quotations_phone ON commercial_quotations (tenant_container_id, company_id, customer_phone);


CREATE TABLE settings_tax (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	rate NUMERIC(12, 8) NOT NULL, 
	is_enabled BOOL NOT NULL, 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_tax_settings_rate_nonnegative CHECK (rate >= 0), 
	CONSTRAINT fk_tax_settings_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_tax_settings_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_tax_settings_company_name UNIQUE (company_id, name), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_tax_settings_container_company ON settings_tax (tenant_container_id, company_id);


CREATE TABLE settings_commission (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	sales_target NUMERIC(14, 3) NOT NULL, 
	commission_interval VARCHAR(16) NOT NULL, 
	commission_percentage NUMERIC(12, 8) NOT NULL, 
	is_active BOOL NOT NULL, 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_commission_settings_target_nonnegative CHECK (sales_target >= 0), 
	CONSTRAINT ck_commission_settings_percentage_nonnegative CHECK (commission_percentage >= 0), 
	CONSTRAINT ck_commission_settings_interval CHECK (commission_interval IN ('daily', 'weekly', 'monthly')), 
	CONSTRAINT fk_commission_settings_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_commission_settings_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_commission_settings_container_company ON settings_commission (tenant_container_id, company_id);


CREATE TABLE settings_global_discount (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	percentage NUMERIC(12, 8) NOT NULL, 
	start_date DATE, 
	end_date DATE, 
	is_active BOOL NOT NULL, 
	description VARCHAR(500), 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_global_discount_settings_percentage_range CHECK (percentage >= 0 AND percentage <= 100), 
	CONSTRAINT fk_global_discount_settings_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_global_discount_settings_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_global_discount_settings_container_company ON settings_global_discount (tenant_container_id, company_id);


CREATE TABLE settings_attendance (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	mandatory_attendance_time VARCHAR(8), 
	is_mandatory_attendance_active BOOL NOT NULL, 
	max_concurrent_breaks INTEGER NOT NULL, 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_attendance_settings_breaks_positive CHECK (max_concurrent_breaks >= 1), 
	CONSTRAINT fk_attendance_settings_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_attendance_settings_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_attendance_settings_company UNIQUE (tenant_container_id, company_id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_attendance_settings_container_company ON settings_attendance (tenant_container_id, company_id);


CREATE TABLE product_categories (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_product_categories_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_product_categories_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_product_categories_company_name UNIQUE (company_id, name), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_product_categories_container_company ON product_categories (tenant_container_id, company_id);


CREATE TABLE scm_suppliers (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	contact_email VARCHAR(254), 
	phone VARCHAR(64), 
	lead_time INTEGER, 
	notes TEXT, 
	supplier_status VARCHAR(16) NOT NULL, 
	created_by_id VARCHAR(64), 
	updated_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_suppliers_status CHECK (supplier_status IN ('active', 'inactive')), 
	CONSTRAINT fk_suppliers_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_suppliers_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_suppliers_container_company_active ON scm_suppliers (tenant_container_id, company_id, supplier_status);


CREATE TABLE stock_audits (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	audit_number VARCHAR(64) NOT NULL, 
	title VARCHAR(160) NOT NULL, 
	store_location VARCHAR(160), 
	admin_id VARCHAR(64), 
	auditor_id VARCHAR(64), 
	status VARCHAR(24) NOT NULL, 
	auditor_selfie_path TEXT, 
	started_at DATETIME, 
	completed_at DATETIME, 
	created_by_id VARCHAR(64), 
	updated_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_stock_audits_status CHECK (status IN ('draft', 'in_progress', 'completed', 'cancelled')), 
	CONSTRAINT fk_stock_audits_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_stock_audits_store_scope FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_stock_audits_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_stock_audits_company_number UNIQUE (company_id, audit_number), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(admin_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(auditor_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_stock_audits_company_store_status ON stock_audits (tenant_container_id, company_id, store_id, status);


CREATE TABLE messaging_conversations (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	subject VARCHAR(160), 
	participant_ids JSON NOT NULL, 
	creator_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_conversations_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_conversations_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(creator_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_conversations_container_created ON messaging_conversations (tenant_container_id, created_at);


CREATE TABLE cloud_files (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	owner_user_id VARCHAR(64) NOT NULL, 
	owner_company_id VARCHAR(64), 
	file_path TEXT NOT NULL, 
	original_name VARCHAR(255) NOT NULL, 
	mime_type VARCHAR(128), 
	size_bytes INTEGER NOT NULL, 
	notes VARCHAR(500), 
	share_scope VARCHAR(16) NOT NULL, 
	share_unit_id VARCHAR(64), 
	is_shared BOOL NOT NULL, 
	uploaded_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_cloud_files_size_nonnegative CHECK (size_bytes >= 0), 
	CONSTRAINT ck_cloud_files_share_scope CHECK (share_scope IN ('container', 'company', 'store', 'user')), 
	CONSTRAINT fk_cloud_files_owner_company FOREIGN KEY(tenant_container_id, owner_company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_cloud_files_container_id UNIQUE (tenant_container_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_cloud_files_container_owner ON cloud_files (tenant_container_id, owner_user_id);


CREATE TABLE tenant_subscriptions (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	plan_id VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	starts_at DATETIME NOT NULL, 
	trial_ends_at DATETIME, 
	current_period_start DATETIME, 
	current_period_end DATETIME, 
	cancel_at_period_end BOOL NOT NULL, 
	updated_by_user_id VARCHAR(64), 
	internal_note TEXT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_tenant_subscriptions_status CHECK (status IN ('trialing', 'active', 'past_due', 'suspended', 'canceled')), 
	CONSTRAINT fk_tenant_subscriptions_container FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	CONSTRAINT uq_tenant_subscriptions_container UNIQUE (tenant_container_id), 
	CONSTRAINT uq_tenant_subscriptions_container_id UNIQUE (tenant_container_id, id), 
	FOREIGN KEY(plan_id) REFERENCES subscription_plans (id) ON DELETE RESTRICT, 
	FOREIGN KEY(updated_by_user_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_tenant_subscriptions_status_period ON tenant_subscriptions (status, current_period_end);


CREATE TABLE platform_audit_events (
	id VARCHAR(64) NOT NULL, 
	actor_user_id VARCHAR(64), 
	tenant_container_id VARCHAR(64), 
	action VARCHAR(64) NOT NULL, 
	entity_type VARCHAR(64) NOT NULL, 
	entity_id VARCHAR(64) NOT NULL, 
	before_data JSON, 
	after_data JSON, 
	reason VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_platform_audit_created ON platform_audit_events (created_at);

CREATE INDEX ix_platform_audit_entity ON platform_audit_events (entity_type, entity_id);


CREATE TABLE plan_change_requests (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	requested_plan_id VARCHAR(64) NOT NULL, 
	requested_by_user_id VARCHAR(64) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	request_note VARCHAR(500), 
	review_note VARCHAR(500), 
	reviewed_by_user_id VARCHAR(64), 
	reviewed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_plan_change_requests_status CHECK (status IN ('pending', 'approved', 'rejected', 'canceled')), 
	CONSTRAINT fk_plan_change_requests_container FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(requested_plan_id) REFERENCES subscription_plans (id) ON DELETE RESTRICT, 
	FOREIGN KEY(requested_by_user_id) REFERENCES users (id) ON DELETE RESTRICT, 
	FOREIGN KEY(reviewed_by_user_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_plan_change_requests_tenant_status_created ON plan_change_requests (tenant_container_id, status, created_at);


CREATE TABLE tenant_data_policy_scopes (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	policy_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	store_id VARCHAR(64), 
	is_allowed BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_tenant_data_policy_scopes_one_unit CHECK ((company_id IS NOT NULL AND store_id IS NULL) OR (company_id IS NULL AND store_id IS NOT NULL)), 
	CONSTRAINT fk_tenant_data_policy_scopes_policy FOREIGN KEY(tenant_container_id, policy_id) REFERENCES tenant_data_policies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_tenant_data_policy_scopes_company FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_tenant_data_policy_scopes_store FOREIGN KEY(tenant_container_id, store_id) REFERENCES stores (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_tenant_data_policy_scopes_unit UNIQUE (tenant_container_id, policy_id, company_id, store_id)
)ENGINE=InnoDB CHARSET=utf8mb4;


CREATE TABLE user_store_assignments (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	user_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	assigned_by_id VARCHAR(64), 
	can_view_shared_bills BOOL NOT NULL, 
	is_active BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_user_store_assignments_membership FOREIGN KEY(tenant_container_id, user_id) REFERENCES container_memberships (tenant_container_id, user_id) ON DELETE CASCADE, 
	CONSTRAINT fk_user_store_assignments_store_scope FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_user_store_assignments_user_store UNIQUE (user_id, store_id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(assigned_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_user_store_assignments_container_user ON user_store_assignments (tenant_container_id, user_id);

CREATE INDEX ix_user_store_assignments_container_store_active ON user_store_assignments (tenant_container_id, store_id, is_active);


CREATE TABLE inventory_balances (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	product_owner_company_id VARCHAR(64) NOT NULL, 
	product_id VARCHAR(64) NOT NULL, 
	quantity_on_hand INTEGER NOT NULL, 
	low_stock_threshold INTEGER, 
	updated_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_inventory_balances_store_scope FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_inventory_balances_product_scope FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_inventory_balances_store_product UNIQUE (tenant_container_id, company_id, store_id, product_owner_company_id, product_id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_inventory_balances_container_store ON inventory_balances (tenant_container_id, store_id);


CREATE TABLE inventory_movements (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	product_owner_company_id VARCHAR(64) NOT NULL, 
	product_id VARCHAR(64) NOT NULL, 
	movement_type VARCHAR(24) NOT NULL, 
	quantity_delta INTEGER NOT NULL, 
	reason VARCHAR(500), 
	actor_user_id VARCHAR(64), 
	idempotency_key VARCHAR(128), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_inventory_movements_type CHECK (movement_type IN ('opening', 'receive', 'adjustment', 'sale', 'return', 'transfer_in', 'transfer_out')), 
	CONSTRAINT fk_inventory_movements_store_scope FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_inventory_movements_product_scope FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE UNIQUE INDEX uq_inventory_movement_actor_idempotency ON inventory_movements (tenant_container_id, actor_user_id, idempotency_key);

CREATE INDEX ix_inventory_movements_product_created ON inventory_movements (tenant_container_id, product_id, created_at);

CREATE INDEX ix_inventory_movements_container_store_created ON inventory_movements (tenant_container_id, store_id, created_at);


CREATE TABLE commercial_demand_notices (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	notice_number VARCHAR(64) NOT NULL, 
	salesperson_id VARCHAR(64), 
	salesperson_name VARCHAR(160), 
	customer_name VARCHAR(160), 
	customer_phone VARCHAR(64) NOT NULL, 
	phone_search VARCHAR(32) NOT NULL, 
	product_owner_company_id VARCHAR(64), 
	product_id VARCHAR(64), 
	product_name VARCHAR(255) NOT NULL, 
	product_sku VARCHAR(128), 
	quantity_requested INTEGER NOT NULL, 
	quantity_fulfilled INTEGER NOT NULL, 
	agreed_price NUMERIC(14, 3), 
	expected_availability_date DATE, 
	payments JSON, 
	amount_paid NUMERIC(14, 3) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	is_new_product BOOL NOT NULL, 
	notes TEXT, 
	created_by_id VARCHAR(64), 
	updated_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_commercial_demand_notices_status CHECK (status IN ('open', 'converted', 'cancelled')), 
	CONSTRAINT ck_commercial_demand_notices_quantity_positive CHECK (quantity_requested > 0), 
	CONSTRAINT ck_commercial_demand_notices_fulfilled_range CHECK (quantity_fulfilled >= 0 AND quantity_fulfilled <= quantity_requested), 
	CONSTRAINT ck_commercial_demand_notices_price_nonnegative CHECK (agreed_price IS NULL OR agreed_price >= 0), 
	CONSTRAINT ck_commercial_demand_notices_product_pair CHECK ((product_owner_company_id IS NULL AND product_id IS NULL) OR (product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)), 
	CONSTRAINT ck_commercial_demand_notices_new_product_bool CHECK (is_new_product IN (0, 1)), 
	CONSTRAINT fk_commercial_demand_notices_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_commercial_demand_notices_store_container FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_commercial_demand_notices_catalog_product FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_commercial_demand_notices_company_number UNIQUE (company_id, notice_number), 
	CONSTRAINT uq_commercial_demand_notices_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(salesperson_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_commercial_demand_notices_phone ON commercial_demand_notices (tenant_container_id, company_id, phone_search);

CREATE INDEX ix_commercial_demand_notices_store_status_date ON commercial_demand_notices (tenant_container_id, company_id, store_id, status, created_at);


CREATE TABLE commercial_quotation_lines (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	quotation_id VARCHAR(64) NOT NULL, 
	line_number INTEGER NOT NULL, 
	product_owner_company_id VARCHAR(64), 
	product_id VARCHAR(64), 
	product_name VARCHAR(255) NOT NULL, 
	product_sku VARCHAR(128), 
	unit_price NUMERIC(14, 3) NOT NULL, 
	quantity INTEGER NOT NULL, 
	line_total NUMERIC(14, 3) NOT NULL, 
	is_external BOOL NOT NULL, 
	converted BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_commercial_quotation_lines_number_positive CHECK (line_number > 0), 
	CONSTRAINT ck_commercial_quotation_lines_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_commercial_quotation_lines_price_positive CHECK (unit_price > 0), 
	CONSTRAINT ck_commercial_quotation_lines_total_positive CHECK (line_total > 0), 
	CONSTRAINT ck_commercial_quotation_lines_external_product_pair CHECK ((is_external = 1 AND product_owner_company_id IS NULL AND product_id IS NULL) OR (is_external = 0 AND product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)), 
	CONSTRAINT ck_commercial_quotation_lines_external_bool CHECK (is_external IN (0, 1)), 
	CONSTRAINT fk_commercial_quotation_lines_quotation_container FOREIGN KEY(tenant_container_id, company_id, quotation_id) REFERENCES commercial_quotations (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_commercial_quotation_lines_catalog_product FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_commercial_quotation_lines_quote_number UNIQUE (tenant_container_id, company_id, quotation_id, line_number), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_commercial_quotation_lines_quote ON commercial_quotation_lines (tenant_container_id, company_id, quotation_id);


CREATE TABLE scm_supplier_products (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	supplier_id VARCHAR(64) NOT NULL, 
	product_owner_company_id VARCHAR(64) NOT NULL, 
	product_id VARCHAR(64) NOT NULL, 
	unit_price NUMERIC(14, 3) NOT NULL, 
	document_path TEXT, 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_supplier_products_unit_price_nonnegative CHECK (unit_price >= 0), 
	CONSTRAINT fk_supplier_products_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_supplier_products_supplier FOREIGN KEY(tenant_container_id, company_id, supplier_id) REFERENCES scm_suppliers (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_supplier_products_product FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_supplier_products_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_supplier_products_supplier_product UNIQUE (company_id, supplier_id, product_owner_company_id, product_id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_supplier_products_container_supplier ON scm_supplier_products (tenant_container_id, supplier_id);


CREATE TABLE scm_supplier_attachments (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	supplier_id VARCHAR(64) NOT NULL, 
	file_path TEXT NOT NULL, 
	original_name VARCHAR(255) NOT NULL, 
	notes VARCHAR(500), 
	uploaded_by_id VARCHAR(64), 
	uploaded_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_supplier_attachments_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_supplier_attachments_supplier FOREIGN KEY(tenant_container_id, company_id, supplier_id) REFERENCES scm_suppliers (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_supplier_attachments_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(uploaded_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_supplier_attachments_container_supplier ON scm_supplier_attachments (tenant_container_id, supplier_id);


CREATE TABLE scm_purchase_orders (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	po_number VARCHAR(64) NOT NULL, 
	supplier_id VARCHAR(64) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	total_amount NUMERIC(14, 3) NOT NULL, 
	advance_paid NUMERIC(14, 3) NOT NULL, 
	deadline DATE, 
	expected_delivery DATE, 
	transportation_details TEXT, 
	invoice_path TEXT, 
	logistics_status VARCHAR(120), 
	received_store_id VARCHAR(64), 
	created_by_id VARCHAR(64), 
	updated_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	confirmed_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_purchase_orders_status CHECK (status IN ('draft', 'confirmed', 'partially_received', 'received', 'cancelled')), 
	CONSTRAINT ck_purchase_orders_total_nonnegative CHECK (total_amount >= 0), 
	CONSTRAINT ck_purchase_orders_advance_nonnegative CHECK (advance_paid >= 0), 
	CONSTRAINT fk_purchase_orders_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_purchase_orders_supplier FOREIGN KEY(tenant_container_id, company_id, supplier_id) REFERENCES scm_suppliers (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_purchase_orders_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_purchase_orders_company_number UNIQUE (company_id, po_number), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_purchase_orders_company_status_created ON scm_purchase_orders (tenant_container_id, company_id, status, created_at);


CREATE TABLE stock_audit_items (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	audit_id VARCHAR(64) NOT NULL, 
	product_owner_company_id VARCHAR(64) NOT NULL, 
	product_id VARCHAR(64) NOT NULL, 
	product_name VARCHAR(255) NOT NULL, 
	product_sku VARCHAR(128), 
	current_stock INTEGER NOT NULL, 
	final_audited_qty INTEGER, 
	notes VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_stock_audit_items_current_stock_nonnegative CHECK (current_stock >= 0), 
	CONSTRAINT ck_stock_audit_items_final_nonnegative CHECK (final_audited_qty IS NULL OR final_audited_qty >= 0), 
	CONSTRAINT fk_stock_audit_items_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_stock_audit_items_audit_container FOREIGN KEY(tenant_container_id, company_id, audit_id) REFERENCES stock_audits (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_stock_audit_items_product FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_stock_audit_items_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_stock_audit_items_audit_product UNIQUE (company_id, audit_id, product_id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_stock_audit_items_container_audit ON stock_audit_items (tenant_container_id, audit_id);


CREATE TABLE messaging_messages (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	conversation_id VARCHAR(64) NOT NULL, 
	sender_id VARCHAR(64), 
	content TEXT NOT NULL, 
	sent_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_messages_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_messages_conversation_container FOREIGN KEY(tenant_container_id, company_id, conversation_id) REFERENCES messaging_conversations (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_messages_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(sender_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_messages_container_conversation_sent ON messaging_messages (tenant_container_id, conversation_id, sent_at);


CREATE TABLE cloud_file_shares (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	file_id VARCHAR(64) NOT NULL, 
	shared_with_user_id VARCHAR(64) NOT NULL, 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_cloud_file_shares_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_cloud_file_shares_file_container FOREIGN KEY(tenant_container_id, file_id) REFERENCES cloud_files (tenant_container_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_cloud_file_shares_file_user UNIQUE (tenant_container_id, file_id, shared_with_user_id), 
	CONSTRAINT uq_cloud_file_shares_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(shared_with_user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_cloud_file_shares_container_recipient ON cloud_file_shares (tenant_container_id, shared_with_user_id);


CREATE TABLE subscription_invoices (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	subscription_id VARCHAR(64) NOT NULL, 
	invoice_number VARCHAR(48) NOT NULL, 
	period_start DATE NOT NULL, 
	period_end DATE NOT NULL, 
	amount_due NUMERIC(12, 3) NOT NULL, 
	currency VARCHAR(3) NOT NULL DEFAULT 'OMR', 
	status VARCHAR(12) NOT NULL, 
	issued_at DATETIME NOT NULL, 
	due_at DATETIME, 
	paid_at DATETIME, 
	paid_reference VARCHAR(128), 
	created_by_user_id VARCHAR(64), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_subscription_invoices_nonnegative_amount CHECK (amount_due >= 0), 
	CONSTRAINT ck_subscription_invoices_status CHECK (status IN ('open', 'paid', 'void')), 
	CONSTRAINT ck_subscription_invoices_valid_period CHECK (period_end > period_start), 
	CONSTRAINT fk_subscription_invoices_scoped_subscription FOREIGN KEY(tenant_container_id, subscription_id) REFERENCES tenant_subscriptions (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_subscription_invoices_subscription_period UNIQUE (subscription_id, period_start), 
	CONSTRAINT uq_subscription_invoices_number UNIQUE (invoice_number), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE RESTRICT, 
	FOREIGN KEY(created_by_user_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_subscription_invoices_tenant_status_due ON subscription_invoices (tenant_container_id, status, due_at);


CREATE TABLE realtime_events (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	store_id VARCHAR(64), 
	product_owner_company_id VARCHAR(64), 
	product_id VARCHAR(64), 
	domain VARCHAR(32) NOT NULL, 
	event_type VARCHAR(48) NOT NULL, 
	payload JSON NOT NULL, 
	recipient_user_id VARCHAR(64), 
	actor_user_id VARCHAR(64), 
	cursor_floor BIGINT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_realtime_events_store_scope FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_realtime_events_product_scope FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE RESTRICT, 
	FOREIGN KEY(recipient_user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_realtime_events_container_store_cursor ON realtime_events (tenant_container_id, store_id, id);

CREATE INDEX ix_realtime_events_domain_cursor ON realtime_events (tenant_container_id, domain, id);

CREATE INDEX ix_realtime_events_container_product_cursor ON realtime_events (tenant_container_id, product_id, id);

CREATE INDEX ix_realtime_events_recipient_cursor ON realtime_events (recipient_user_id, id);


CREATE TABLE sales_orders (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	origin_store_id VARCHAR(64) NOT NULL, 
	customer_name VARCHAR(160), 
	customer_phone VARCHAR(64) NOT NULL, 
	phone_search VARCHAR(32) NOT NULL, 
	order_number VARCHAR(64) NOT NULL, 
	source_demand_notice_id VARCHAR(64), 
	source_quotation_id VARCHAR(64), 
	source_return_id VARCHAR(64), 
	checkout_idempotency_key VARCHAR(128), 
	checkout_request_hash VARCHAR(64), 
	subtotal_amount NUMERIC(14, 3) NOT NULL, 
	discount_amount NUMERIC(14, 3) NOT NULL, 
	applied_discount_percentage NUMERIC(12, 8) NOT NULL, 
	applied_global_discount_percentage NUMERIC(12, 8) NOT NULL, 
	taxes JSON, 
	delivery_status VARCHAR(24) NOT NULL, 
	delivery_address TEXT, 
	storekeeper_notes VARCHAR(500), 
	cashier_notes VARCHAR(500), 
	reminder_date DATE, 
	reminder_notes VARCHAR(500), 
	primary_salesperson_id VARCHAR(64), 
	secondary_salesperson_id VARCHAR(64), 
	primary_commission_rate NUMERIC(12, 8), 
	secondary_commission_rate NUMERIC(12, 8), 
	business_date DATE NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	total_amount NUMERIC(14, 3) NOT NULL, 
	invoice_category VARCHAR(24), 
	invoice_number VARCHAR(64), 
	created_by_id VARCHAR(64), 
	updated_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	closed_at DATETIME, 
	voided_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_sales_orders_status CHECK (status IN ('open', 'closed', 'voided')), 
	CONSTRAINT ck_sales_orders_delivery_status CHECK (delivery_status IN ('pending', 'partially_delivered', 'delivered', 'cancelled')), 
	CONSTRAINT ck_sales_orders_total_nonnegative CHECK (total_amount >= 0), 
	CONSTRAINT ck_sales_orders_subtotal_nonnegative CHECK (subtotal_amount >= 0), 
	CONSTRAINT ck_sales_orders_discount_nonnegative CHECK (discount_amount >= 0), 
	CONSTRAINT ck_sales_orders_discount_pct_range CHECK (applied_discount_percentage >= 0 AND applied_discount_percentage <= 100), 
	CONSTRAINT ck_sales_orders_global_discount_pct_range CHECK (applied_global_discount_percentage >= 0 AND applied_global_discount_percentage <= 100), 
	CONSTRAINT ck_sales_orders_invoice_category CHECK (invoice_category IS NULL OR invoice_category IN ('cash', 'bank', 'bank_transfer', 'other')), 
	CONSTRAINT ck_sales_orders_one_commercial_source CHECK (source_demand_notice_id IS NULL OR source_quotation_id IS NULL), 
	CONSTRAINT fk_sales_orders_source_demand_notice FOREIGN KEY(tenant_container_id, company_id, source_demand_notice_id) REFERENCES commercial_demand_notices (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sales_orders_source_quotation FOREIGN KEY(tenant_container_id, company_id, source_quotation_id) REFERENCES commercial_quotations (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sales_orders_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sales_orders_origin_store_container FOREIGN KEY(tenant_container_id, company_id, origin_store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_sales_orders_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT uq_sales_orders_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	CONSTRAINT uq_sales_orders_company_order_number UNIQUE (company_id, order_number), 
	CONSTRAINT uq_sales_orders_company_invoice UNIQUE (company_id, invoice_number), 
	CONSTRAINT uq_sales_orders_source_quotation UNIQUE (company_id, source_quotation_id), 
	CONSTRAINT uq_sales_orders_company_checkout_idempotency UNIQUE (company_id, checkout_idempotency_key), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(primary_salesperson_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(secondary_salesperson_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(updated_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_sales_orders_phone_status_date ON sales_orders (tenant_container_id, company_id, phone_search, status, business_date);

CREATE INDEX ix_sales_orders_company_store_status ON sales_orders (tenant_container_id, company_id, origin_store_id, status);


CREATE TABLE scm_po_items (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	po_id VARCHAR(64) NOT NULL, 
	product_owner_company_id VARCHAR(64) NOT NULL, 
	product_id VARCHAR(64) NOT NULL, 
	quantity_ordered INTEGER NOT NULL, 
	quantity_received INTEGER NOT NULL, 
	unit_price NUMERIC(14, 3) NOT NULL, 
	notes TEXT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_po_items_quantity_ordered_positive CHECK (quantity_ordered > 0), 
	CONSTRAINT ck_po_items_quantity_received_nonnegative CHECK (quantity_received >= 0), 
	CONSTRAINT ck_po_items_unit_price_nonnegative CHECK (unit_price >= 0), 
	CONSTRAINT fk_po_items_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_po_items_po_container FOREIGN KEY(tenant_container_id, company_id, po_id) REFERENCES scm_purchase_orders (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_po_items_product FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_po_items_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_po_items_container_po ON scm_po_items (tenant_container_id, po_id);


CREATE TABLE scm_po_attachments (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	po_id VARCHAR(64) NOT NULL, 
	file_path TEXT NOT NULL, 
	original_name VARCHAR(255) NOT NULL, 
	attachment_type VARCHAR(24) NOT NULL, 
	notes VARCHAR(500), 
	uploaded_by_id VARCHAR(64), 
	uploaded_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_po_attachments_type CHECK (attachment_type IN ('invoice', 'shipping', 'other')), 
	CONSTRAINT fk_po_attachments_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_po_attachments_po_container FOREIGN KEY(tenant_container_id, company_id, po_id) REFERENCES scm_purchase_orders (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_po_attachments_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(uploaded_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_po_attachments_container_po ON scm_po_attachments (tenant_container_id, po_id);


CREATE TABLE stock_audit_item_counts (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	audit_item_id VARCHAR(64) NOT NULL, 
	count INTEGER NOT NULL, 
	notes VARCHAR(500), 
	counted_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_stock_audit_item_counts_nonnegative CHECK (count >= 0), 
	CONSTRAINT fk_stock_audit_item_counts_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_stock_audit_item_counts_item_container FOREIGN KEY(tenant_container_id, company_id, audit_item_id) REFERENCES stock_audit_items (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_stock_audit_item_counts_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(counted_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_stock_audit_item_counts_container_item ON stock_audit_item_counts (tenant_container_id, audit_item_id);


CREATE TABLE messaging_message_recipients (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	message_id VARCHAR(64) NOT NULL, 
	recipient_id VARCHAR(64) NOT NULL, 
	recipient_type VARCHAR(16) NOT NULL, 
	read_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_message_recipients_type CHECK (recipient_type IN ('user', 'role')), 
	CONSTRAINT fk_message_recipients_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_message_recipients_message_container FOREIGN KEY(tenant_container_id, company_id, message_id) REFERENCES messaging_messages (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_message_recipients_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_message_recipients_container_recipient ON messaging_message_recipients (tenant_container_id, recipient_id);


CREATE TABLE messaging_attachments (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64), 
	message_id VARCHAR(64) NOT NULL, 
	file_path TEXT NOT NULL, 
	original_name VARCHAR(255) NOT NULL, 
	mime_type VARCHAR(128), 
	uploaded_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_attachments_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_attachments_message_container FOREIGN KEY(tenant_container_id, company_id, message_id) REFERENCES messaging_messages (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_attachments_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_attachments_container_message ON messaging_attachments (tenant_container_id, message_id);


CREATE TABLE sales_order_lines (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	order_id VARCHAR(64) NOT NULL, 
	product_owner_company_id VARCHAR(64), 
	product_id VARCHAR(64), 
	added_store_id VARCHAR(64) NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	sku VARCHAR(128), 
	quantity INTEGER NOT NULL, 
	unit_price NUMERIC(14, 3) NOT NULL, 
	line_total NUMERIC(14, 3) NOT NULL, 
	is_active BOOL NOT NULL, 
	created_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	removed_at DATETIME, 
	removed_by_id VARCHAR(64), 
	removal_reason VARCHAR(500), 
	PRIMARY KEY (id), 
	CONSTRAINT ck_sales_order_lines_quantity_nonnegative CHECK (quantity >= 0), 
	CONSTRAINT ck_sales_order_lines_unit_price_nonnegative CHECK (unit_price >= 0), 
	CONSTRAINT ck_sales_order_lines_line_total_nonnegative CHECK (line_total >= 0), 
	CONSTRAINT ck_sales_order_lines_quantity_active CHECK ((is_active = 1 AND quantity > 0) OR (is_active = 0 AND quantity = 0)), 
	CONSTRAINT ck_sales_order_lines_product_link_pair CHECK ((product_owner_company_id IS NULL AND product_id IS NULL) OR (product_owner_company_id IS NOT NULL AND product_id IS NOT NULL)), 
	CONSTRAINT fk_sales_order_lines_catalog_product FOREIGN KEY(tenant_container_id, product_owner_company_id, product_id) REFERENCES catalog_products (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sales_order_lines_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_sales_order_lines_order_container FOREIGN KEY(tenant_container_id, company_id, order_id) REFERENCES sales_orders (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_sales_order_lines_store_container FOREIGN KEY(tenant_container_id, company_id, added_store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_sales_order_lines_company_id_id UNIQUE (company_id, id), 
	CONSTRAINT uq_sales_order_lines_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(removed_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_sales_order_lines_order_active ON sales_order_lines (tenant_container_id, company_id, order_id, is_active);


CREATE TABLE order_payments (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	order_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	method VARCHAR(24) NOT NULL, 
	amount NUMERIC(14, 3) NOT NULL, 
	idempotency_key VARCHAR(128), 
	transaction_reference VARCHAR(128), 
	received_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_payments_method CHECK (method IN ('cash', 'bank', 'bank_transfer', 'other')), 
	CONSTRAINT ck_order_payments_amount_positive CHECK (amount > 0), 
	CONSTRAINT fk_order_payments_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_order_payments_order_container FOREIGN KEY(tenant_container_id, company_id, order_id) REFERENCES sales_orders (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_order_payments_store_container FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_order_payments_company_idempotency UNIQUE (company_id, idempotency_key), 
	CONSTRAINT uq_order_payments_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(received_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_order_payments_company_store_created ON order_payments (tenant_container_id, company_id, store_id, created_at);

CREATE INDEX ix_order_payments_company_order ON order_payments (tenant_container_id, company_id, order_id);


CREATE TABLE order_returns (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	order_id VARCHAR(64) NOT NULL, 
	store_id VARCHAR(64) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	refund_method VARCHAR(24) NOT NULL, 
	refund_amount NUMERIC(14, 3) NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	transaction_reference VARCHAR(128), 
	exchange_order_id VARCHAR(64), 
	processed_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_returns_kind CHECK (kind IN ('refund', 'exchange', 'store_credit')), 
	CONSTRAINT ck_order_returns_refund_method CHECK (refund_method IN ('cash', 'bank', 'bank_transfer', 'other')), 
	CONSTRAINT ck_order_returns_refund_amount_positive CHECK (refund_amount > 0), 
	CONSTRAINT fk_order_returns_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_order_returns_order_container FOREIGN KEY(tenant_container_id, company_id, order_id) REFERENCES sales_orders (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_order_returns_store_container FOREIGN KEY(tenant_container_id, company_id, store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_order_returns_company_idempotency UNIQUE (company_id, idempotency_key), 
	CONSTRAINT uq_order_returns_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(processed_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_order_returns_company_store_created ON order_returns (tenant_container_id, company_id, store_id, created_at);

CREATE INDEX ix_order_returns_company_order_created ON order_returns (tenant_container_id, company_id, order_id, created_at);


CREATE TABLE commercial_demand_notice_fulfillments (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	notice_id VARCHAR(64) NOT NULL, 
	order_id VARCHAR(64) NOT NULL, 
	quantity INTEGER NOT NULL, 
	deposit_applied NUMERIC(14, 3) NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	fulfilled_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_demand_notice_fulfillments_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT fk_demand_notice_fulfillments_notice FOREIGN KEY(tenant_container_id, company_id, notice_id) REFERENCES commercial_demand_notices (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_demand_notice_fulfillments_order FOREIGN KEY(tenant_container_id, company_id, order_id) REFERENCES sales_orders (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_demand_notice_fulfillment_key UNIQUE (company_id, notice_id, idempotency_key), 
	CONSTRAINT uq_demand_notice_fulfillment_container_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(fulfilled_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_demand_notice_fulfillment_notice ON commercial_demand_notice_fulfillments (tenant_container_id, company_id, notice_id, created_at);


CREATE TABLE stock_audit_images (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	count_event_id VARCHAR(64) NOT NULL, 
	image_path TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT fk_stock_audit_images_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_stock_audit_images_count_container FOREIGN KEY(tenant_container_id, company_id, count_event_id) REFERENCES stock_audit_item_counts (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT uq_stock_audit_images_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_stock_audit_images_container_count ON stock_audit_images (tenant_container_id, count_event_id);


CREATE TABLE order_removal_requests (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	order_id VARCHAR(64) NOT NULL, 
	line_id VARCHAR(64) NOT NULL, 
	requesting_store_id VARCHAR(64) NOT NULL, 
	quantity_to_remove INTEGER NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	requested_by_id VARCHAR(64), 
	reviewed_by_id VARCHAR(64), 
	review_reason VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	reviewed_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_removal_requests_status CHECK (status IN ('pending', 'approved', 'rejected')), 
	CONSTRAINT ck_order_removal_requests_quantity_positive CHECK (quantity_to_remove > 0), 
	CONSTRAINT fk_order_removal_requests_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_order_removal_requests_order_container FOREIGN KEY(tenant_container_id, company_id, order_id) REFERENCES sales_orders (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_order_removal_requests_line_container FOREIGN KEY(tenant_container_id, company_id, line_id) REFERENCES sales_order_lines (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_order_removal_requests_store_container FOREIGN KEY(tenant_container_id, company_id, requesting_store_id) REFERENCES stores (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(requested_by_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(reviewed_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_order_removal_requests_company_store_status ON order_removal_requests (tenant_container_id, company_id, requesting_store_id, status);


CREATE TABLE store_credits (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	credit_number VARCHAR(64) NOT NULL, 
	customer_name VARCHAR(160), 
	customer_phone VARCHAR(64) NOT NULL, 
	phone_search VARCHAR(32) NOT NULL, 
	amount NUMERIC(14, 3) NOT NULL, 
	remaining_amount NUMERIC(14, 3) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	expires_at DATETIME, 
	source_order_id VARCHAR(64), 
	source_return_id VARCHAR(64), 
	issued_by_id VARCHAR(64), 
	reason VARCHAR(500), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_store_credits_amount_positive CHECK (amount > 0), 
	CONSTRAINT ck_store_credits_remaining_nonnegative CHECK (remaining_amount >= 0), 
	CONSTRAINT ck_store_credits_remaining_range CHECK (remaining_amount <= amount), 
	CONSTRAINT ck_store_credits_status CHECK (status IN ('open', 'fully_used', 'expired', 'voided')), 
	CONSTRAINT fk_store_credits_company_container FOREIGN KEY(tenant_container_id, company_id) REFERENCES companies (tenant_container_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_store_credits_source_order FOREIGN KEY(tenant_container_id, company_id, source_order_id) REFERENCES sales_orders (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_store_credits_source_return FOREIGN KEY(tenant_container_id, company_id, source_return_id) REFERENCES order_returns (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_store_credits_company_number UNIQUE (company_id, credit_number), 
	CONSTRAINT uq_store_credits_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(issued_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_store_credits_company_phone ON store_credits (tenant_container_id, company_id, phone_search);


CREATE TABLE order_return_lines (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	return_id VARCHAR(64) NOT NULL, 
	sales_order_line_id VARCHAR(64) NOT NULL, 
	quantity INTEGER NOT NULL, 
	unit_price NUMERIC(14, 3) NOT NULL, 
	line_total NUMERIC(14, 3) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_return_lines_quantity_positive CHECK (quantity > 0), 
	CONSTRAINT ck_order_return_lines_unit_price_nonnegative CHECK (unit_price >= 0), 
	CONSTRAINT ck_order_return_lines_total_nonnegative CHECK (line_total >= 0), 
	CONSTRAINT fk_order_return_lines_return_container FOREIGN KEY(tenant_container_id, company_id, return_id) REFERENCES order_returns (tenant_container_id, company_id, id) ON DELETE CASCADE, 
	CONSTRAINT fk_order_return_lines_order_line_container FOREIGN KEY(tenant_container_id, company_id, sales_order_line_id) REFERENCES sales_order_lines (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_order_return_lines_return_line UNIQUE (tenant_container_id, company_id, return_id, sales_order_line_id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_order_return_lines_container_line ON order_return_lines (tenant_container_id, company_id, sales_order_line_id);


CREATE TABLE store_credit_redemptions (
	id VARCHAR(64) NOT NULL, 
	tenant_container_id VARCHAR(64) NOT NULL, 
	company_id VARCHAR(64) NOT NULL, 
	store_credit_id VARCHAR(64) NOT NULL, 
	order_id VARCHAR(64) NOT NULL, 
	payment_id VARCHAR(64) NOT NULL, 
	amount NUMERIC(14, 3) NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	processed_by_id VARCHAR(64), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_store_credit_redemptions_amount_positive CHECK (amount > 0), 
	CONSTRAINT fk_store_credit_redemptions_credit FOREIGN KEY(tenant_container_id, company_id, store_credit_id) REFERENCES store_credits (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_store_credit_redemptions_order FOREIGN KEY(tenant_container_id, company_id, order_id) REFERENCES sales_orders (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT fk_store_credit_redemptions_payment FOREIGN KEY(tenant_container_id, company_id, payment_id) REFERENCES order_payments (tenant_container_id, company_id, id) ON DELETE RESTRICT, 
	CONSTRAINT uq_store_credit_redemptions_company_idempotency UNIQUE (company_id, idempotency_key), 
	CONSTRAINT uq_store_credit_redemptions_container_company_id UNIQUE (tenant_container_id, company_id, id), 
	FOREIGN KEY(tenant_container_id) REFERENCES tenant_containers (id) ON DELETE CASCADE, 
	FOREIGN KEY(processed_by_id) REFERENCES users (id) ON DELETE SET NULL
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE INDEX ix_store_credit_redemptions_container_credit ON store_credit_redemptions (tenant_container_id, store_credit_id);
