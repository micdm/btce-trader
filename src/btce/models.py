from sqlalchemy import Column, DateTime, Numeric, Integer, SmallInteger, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


class Tick(Base):

    __tablename__ = 'ticks'

    create_date = Column(DateTime, primary_key=True)
    value = Column(Numeric)


class Trade(Base):

    __tablename__ = 'trades'

    id = Column(Integer, primary_key=True)
    create_date = Column(DateTime)
    type = Column(SmallInteger)
    amount = Column(Numeric)
    price = Column(Numeric)


class Order(Base):

    __tablename__ = 'orders'
    __table_args__ = (
        PrimaryKeyConstraint('actual_date', 'type', 'amount', 'price'),
    )

    actual_date = Column(DateTime)
    type = Column(SmallInteger)
    amount = Column(Numeric)
    price = Column(Numeric)


def synchronize(engine):
    Base.metadata.create_all(engine)
