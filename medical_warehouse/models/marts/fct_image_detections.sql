{{
    config(
        materialized='table',
        schema='marts'
    )
}}

with raw_yolo as (
    select * from {{ source('raw', 'yolo_detections') }}
),

staging_messages as (
    select * from {{ ref('stg_telegram_messages') }}
),

dim_channels as (
    select * from {{ ref('dim_channels') }}
),

dim_dates as (
    select * from {{ ref('dim_dates') }}
),

fct_image_detections as (
    select
        -- Fact grain: one row per image detection
        ry.message_id,

        -- Foreign keys
        dc.channel_key,
        dd.date_key,

        -- Image metadata
        ry.image_path,
        sm.message_text,

        -- Detection metrics
        ry.detected_objects_count,
        ry.top_detected_class,
        ry.top_confidence,

        -- Classification
        ry.image_category,

        -- Engagement metrics from messages
        sm.views as view_count,
        sm.forwards as forward_count,

        -- Calculated metrics
        case
            when sm.views > 0 then round((sm.forwards::numeric / sm.views) * 100, 2)
            else 0
        end as forward_rate_pct,

        -- Metadata
        sm.message_date,
        ry.loaded_at

    from raw_yolo ry
    inner join staging_messages sm
        on ry.message_id = sm.message_id
        and ry.channel_name = sm.channel_name
    inner join dim_channels dc
        on sm.channel_name = dc.channel_name
    inner join dim_dates dd
        on date_trunc('day', sm.message_date) = dd.full_date
)

select * from fct_image_detections
