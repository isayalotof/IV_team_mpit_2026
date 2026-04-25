-- Read-only user for AskData
CREATE USER askdata_reader WITH PASSWORD 'reader_password';

-- Main orders/tenders table (real Drivee data)
-- One row = one tender (offer to a specific driver).
-- One order_id → many tender_id rows (one per driver candidate).
-- tender_id can be NULL when the row describes an order without a specific tender.
CREATE TABLE anonymized_incity_orders (
    city_id                         INTEGER NOT NULL,
    order_id                        TEXT NOT NULL,
    tender_id                       TEXT,
    user_id                         TEXT,
    driver_id                       TEXT,
    offset_hours                    SMALLINT,
    status_order                    TEXT,
    status_tender                   TEXT,
    order_timestamp                 TIMESTAMPTZ,
    tender_timestamp                TIMESTAMPTZ,
    driveraccept_timestamp          TIMESTAMPTZ,
    driverarrived_timestamp         TIMESTAMPTZ,
    driverstarttheride_timestamp    TIMESTAMPTZ,
    driverdone_timestamp            TIMESTAMPTZ,
    clientcancel_timestamp          TIMESTAMPTZ,
    drivercancel_timestamp          TIMESTAMPTZ,
    order_modified_local            TIMESTAMPTZ,
    cancel_before_accept_local      TIMESTAMPTZ,
    distance_in_meters              NUMERIC,
    duration_in_seconds             NUMERIC,
    price_order_local               NUMERIC,
    price_tender_local              NUMERIC,
    price_start_local               NUMERIC
);

CREATE INDEX idx_aio_order_ts ON anonymized_incity_orders (order_timestamp);
CREATE INDEX idx_aio_city     ON anonymized_incity_orders (city_id);
CREATE INDEX idx_aio_status   ON anonymized_incity_orders (status_order);
CREATE INDEX idx_aio_driver   ON anonymized_incity_orders (driver_id);
CREATE INDEX idx_aio_user     ON anonymized_incity_orders (user_id);
CREATE INDEX idx_aio_clcancel ON anonymized_incity_orders (clientcancel_timestamp) WHERE clientcancel_timestamp IS NOT NULL;
CREATE INDEX idx_aio_drcancel ON anonymized_incity_orders (drivercancel_timestamp) WHERE drivercancel_timestamp IS NOT NULL;

-- Daily passenger metrics (one row = one passenger × city × day)
CREATE TABLE passenger_daily_stats (
    city_id                     INTEGER NOT NULL,
    user_id                     TEXT NOT NULL,
    order_date_part             DATE NOT NULL,
    user_reg_date               DATE,
    orders_count                INTEGER,
    orders_cnt_with_tenders     INTEGER,
    orders_cnt_accepted         INTEGER,
    rides_count                 INTEGER,
    rides_time_sum_seconds      NUMERIC,
    online_time_sum_seconds     NUMERIC,
    client_cancel_after_accept  INTEGER
);

CREATE INDEX idx_pds_user     ON passenger_daily_stats (user_id);
CREATE INDEX idx_pds_date     ON passenger_daily_stats (order_date_part);
CREATE INDEX idx_pds_city     ON passenger_daily_stats (city_id);
CREATE INDEX idx_pds_reg_date ON passenger_daily_stats (user_reg_date);

-- Daily driver metrics (one row = one driver × city × day)
CREATE TABLE driver_daily_stats (
    city_id                     INTEGER NOT NULL,
    driver_id                   TEXT NOT NULL,
    tender_date_part            DATE NOT NULL,
    driver_reg_date             DATE,
    orders                      INTEGER,
    orders_cnt_with_tenders     INTEGER,
    orders_cnt_accepted         INTEGER,
    rides_count                 INTEGER,
    rides_time_sum_seconds      NUMERIC,
    online_time_sum_seconds     NUMERIC,
    client_cancel_after_accept  INTEGER
);

CREATE INDEX idx_dds_driver   ON driver_daily_stats (driver_id);
CREATE INDEX idx_dds_date     ON driver_daily_stats (tender_date_part);
CREATE INDEX idx_dds_city     ON driver_daily_stats (city_id);
CREATE INDEX idx_dds_reg_date ON driver_daily_stats (driver_reg_date);

-- City reference (populated from data after import)
CREATE TABLE cities (
    city_id INTEGER PRIMARY KEY,
    name    TEXT NOT NULL
);

-- Read-only grants
GRANT CONNECT ON DATABASE drivee TO askdata_reader;
GRANT USAGE ON SCHEMA public TO askdata_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO askdata_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO askdata_reader;
