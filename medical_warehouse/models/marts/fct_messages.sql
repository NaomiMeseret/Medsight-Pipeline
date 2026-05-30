{{
    config(
        materialized='table',
        schema='marts'
    )
}}

with staging_messages as (
    select * from {{ ref('stg_telegram_messages') }}
),

dim_channels as (
    select * from {{ ref('dim_channels') }}
),

dim_dates as (
    select * from {{ ref('dim_dates') }}
),

fct_messages as (
    select
        -- Fact grain: one row per message
        sm.message_id,
        
        -- Foreign keys
        dc.channel_key,
        dd.date_key,
        sm.channel_name,
        
        -- Message content
        sm.message_text,
        sm.message_length,
        
        -- Media flags
        sm.has_media,
        sm.has_image,
        sm.image_path,
        
        -- Engagement metrics
        sm.views as view_count,
        sm.forwards as forward_count,
        
        -- Calculated metrics
        case 
            when sm.views > 0 then round((sm.forwards::numeric / sm.views) * 100, 2)
            else 0
        end as forward_rate_pct,
        
        -- Metadata
        sm.message_date,
        sm.loaded_at
        
    from staging_messages sm
    inner join dim_channels dc
        on sm.channel_name = dc.channel_name
    inner join dim_dates dd
        on date_trunc('day', sm.message_date) = dd.full_date
)

select * from fct_messages
