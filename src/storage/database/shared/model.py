from coze_coding_dev_sdk.database import Base

from typing import Optional
import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Double, Float, ForeignKey, Index, Integer, Numeric, PrimaryKeyConstraint, String, Table, Text, text, func
from sqlalchemy.dialects.postgresql import OID
from sqlalchemy.orm import Mapped, mapped_column


class HealthCheck(Base):
    __tablename__ = 'health_check'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='health_check_pkey'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), server_default=text('now()'))


t_pg_stat_statements = Table(
    'pg_stat_statements', Base.metadata,
    Column('userid', OID),
    Column('dbid', OID),
    Column('toplevel', Boolean),
    Column('queryid', BigInteger),
    Column('query', Text),
    Column('plans', BigInteger),
    Column('total_plan_time', Double(53)),
    Column('min_plan_time', Double(53)),
    Column('max_plan_time', Double(53)),
    Column('mean_plan_time', Double(53)),
    Column('stddev_plan_time', Double(53)),
    Column('calls', BigInteger),
    Column('total_exec_time', Double(53)),
    Column('min_exec_time', Double(53)),
    Column('max_exec_time', Double(53)),
    Column('mean_exec_time', Double(53)),
    Column('stddev_exec_time', Double(53)),
    Column('rows', BigInteger),
    Column('shared_blks_hit', BigInteger),
    Column('shared_blks_read', BigInteger),
    Column('shared_blks_dirtied', BigInteger),
    Column('shared_blks_written', BigInteger),
    Column('local_blks_hit', BigInteger),
    Column('local_blks_read', BigInteger),
    Column('local_blks_dirtied', BigInteger),
    Column('local_blks_written', BigInteger),
    Column('temp_blks_read', BigInteger),
    Column('temp_blks_written', BigInteger),
    Column('shared_blk_read_time', Double(53)),
    Column('shared_blk_write_time', Double(53)),
    Column('local_blk_read_time', Double(53)),
    Column('local_blk_write_time', Double(53)),
    Column('temp_blk_read_time', Double(53)),
    Column('temp_blk_write_time', Double(53)),
    Column('wal_records', BigInteger),
    Column('wal_fpi', BigInteger),
    Column('wal_bytes', Numeric),
    Column('jit_functions', BigInteger),
    Column('jit_generation_time', Double(53)),
    Column('jit_inspection_count', BigInteger),
    Column('jit_inspection_time', Double(53)),
    Column('jit_inlining_count', BigInteger),
    Column('jit_inlining_time', Double(53)),
    Column('jit_optimization_count', BigInteger),
    Column('jit_optimization_time', Double(53)),
    Column('jit_emission_count', BigInteger),
    Column('jit_emission_time', Double(53)),
    Column('jit_deform_count', BigInteger),
    Column('jit_deform_time', Double(53)),
    Column('stats_since', DateTime(True)),
    Column('minmax_stats_since', DateTime(True))
)


t_pg_stat_statements_info = Table(
    'pg_stat_statements_info', Base.metadata,
    Column('dealloc', BigInteger),
    Column('stats_reset', DateTime(True))
)


# ============================================================
# 情绪出口业务表
# ============================================================

class PartnerProfile(Base):
    """搭子匹配信息"""
    __tablename__ = 'partner_profiles'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="用户标识")
    nickname: Mapped[str] = mapped_column(String(64), nullable=False, comment="昵称")
    city: Mapped[str] = mapped_column(String(64), nullable=False, comment="所在城市")
    activity: Mapped[str] = mapped_column(String(64), nullable=False, comment="想要的活动类型")
    tags: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="标签，逗号分隔")
    contact: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, comment="联系方式")
    bio: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="个人介绍")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("partner_profiles_city_idx", "city"),
        Index("partner_profiles_activity_idx", "activity"),
        Index("partner_profiles_user_id_idx", "user_id"),
    )


class CheckinRecord(Base):
    """日常打卡记录"""
    __tablename__ = 'checkin_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="用户标识")
    checkin_date: Mapped[str] = mapped_column(String(10), nullable=False, comment="打卡日期 YYYY-MM-DD")
    eat_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="饮食评分 0-10")
    move_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="运动评分 0-10")
    sleep_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="睡眠评分 0-10")
    mood_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, comment="心情评分 0-10")
    notes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="备注")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("checkin_records_user_date_idx", "user_id", "checkin_date", unique=True),
        Index("checkin_records_user_id_idx", "user_id"),
    )


class EmergencyContact(Base):
    """紧急联系人"""
    __tablename__ = 'emergency_contacts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="用户标识")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="联系人姓名")
    phone: Mapped[str] = mapped_column(String(32), nullable=False, comment="联系电话")
    relationship: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="与用户关系")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("emergency_contacts_user_id_idx", "user_id"),
    )


class MoodRecord(Base):
    """情绪记录"""
    __tablename__ = 'mood_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="用户标识")
    mood_score: Mapped[float] = mapped_column(Float, nullable=False, comment="情绪评分 0-10")
    mood_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, comment="情绪标签")
    notes: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="情绪描述")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("mood_records_user_id_idx", "user_id"),
        Index("mood_records_created_at_idx", "created_at"),
    )


class NotificationSchedule(Base):
    """定时推送计划"""
    __tablename__ = 'notification_schedules'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, comment="用户标识")
    channel: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'console'"), comment="推送渠道: console/wechat/feishu")
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False, comment="推送类型: morning/greeting/checkin_reminder/anchor_reminder")
    schedule_time: Mapped[str] = mapped_column(String(8), nullable=False, comment="推送时间 HH:MM")
    message_template: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="消息模板")
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text('true'), nullable=False, comment="是否启用")
    last_sent_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True), nullable=True, comment="最近发送时间")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("notification_schedules_user_id_idx", "user_id"),
        Index("notification_schedules_active_idx", "is_active", "schedule_time"),
    )