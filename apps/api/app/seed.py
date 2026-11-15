from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from .models import (
    Animal, AnimalHealthEvent, Buyer, CompostBatch, CompostApplication, Consent, Delivery,
    Farm, FarmMember, FeedAllocation, FeedBatch, Herd, ManureRecord, Organization,
    OrganizationMember, Plot, ProductLot, ProductionRecord, User, UserRole,
)

FARM_ID = UUID("8b1199df-8901-4ba2-9e33-c191f20d43ea")
FARMER_ID = UUID("8b1199df-8901-4ba2-9e33-c191f20d4301")
VET_ID = UUID("8b1199df-8901-4ba2-9e33-c191f20d4302")
COOP_ID = UUID("8b1199df-8901-4ba2-9e33-c191f20d4303")


def seed(db: Session) -> None:
    if db.query(Farm).first():
        return
    farmer = User(id=FARMER_ID, display_name="Amina Njeri", email="farmer@terravanta.demo")
    vet = User(id=VET_ID, display_name="Dr. Kamau (demo)", email="vet@terravanta.demo")
    coop = User(id=COOP_ID, display_name="Kiambu Dairy Cooperative (demo)", email="cooperative@terravanta.demo")
    db.add_all([farmer, vet, coop])
    db.flush()
    db.add_all([UserRole(user_id=FARMER_ID, role="farmer"), UserRole(user_id=VET_ID, role="veterinarian"), UserRole(user_id=COOP_ID, role="cooperative_admin")])
    farm = Farm(id=FARM_ID, code="TV-KBU-0042", name="Greenridge Mixed Farm", owner_name="Amina Njeri", county="Kiambu", subcounty="Githunguri", latitude=-1.0561, longitude=36.7779, size_acres=6.4, farming_system="mixed dairy and horticulture", production_activities=["Dairy cattle", "Fodder", "Maize", "Horticulture"], verification_status="farmer_submitted", is_synthetic=True, created_by=FARMER_ID)
    db.add(farm)
    db.flush()
    db.add_all([FarmMember(farm_id=FARM_ID, user_id=FARMER_ID, role="owner"), FarmMember(farm_id=FARM_ID, user_id=VET_ID, role="veterinarian")])
    herd = Herd(farm_id=FARM_ID, name="Lactating herd")
    db.add(herd)
    db.flush()
    animals = [
        Animal(id=UUID("8b1199df-8901-4ba2-9e33-c191f20d4401"), farm_id=FARM_ID, herd_id=herd.id, tag="KBU-021", name="Maua", species="Cattle", breed="Friesian cross", sex="female", date_of_birth=date(2020, 7, 11)),
        Animal(id=UUID("8b1199df-8901-4ba2-9e33-c191f20d4402"), farm_id=FARM_ID, herd_id=herd.id, tag="KBU-022", name="Tumaini", species="Cattle", breed="Ayrshire cross", sex="female", date_of_birth=date(2019, 10, 4)),
        Animal(id=UUID("8b1199df-8901-4ba2-9e33-c191f20d4403"), farm_id=FARM_ID, herd_id=herd.id, tag="KBU-023", name="Baraka", species="Cattle", breed="Friesian cross", sex="male", date_of_birth=date(2022, 3, 22)),
        Animal(id=UUID("8b1199df-8901-4ba2-9e33-c191f20d4404"), farm_id=FARM_ID, herd_id=herd.id, tag="KBU-024", name="Zuri", species="Cattle", breed="Jersey cross", sex="female", date_of_birth=date(2021, 12, 1)),
    ]
    db.add_all(animals)
    plots = [
        Plot(id=UUID("8b1199df-8901-4ba2-9e33-c191f20d4501"), farm_id=FARM_ID, name="North fodder strip", area_acres=1.2, crop_type="Napier grass", planting_date=date(2025, 2, 15), is_feed_crop=True),
        Plot(id=UUID("8b1199df-8901-4ba2-9e33-c191f20d4502"), farm_id=FARM_ID, name="Lower maize plot", area_acres=1.5, crop_type="Maize", planting_date=date(2025, 3, 4), is_feed_crop=False),
        Plot(id=UUID("8b1199df-8901-4ba2-9e33-c191f20d4503"), farm_id=FARM_ID, name="Kitchen garden", area_acres=0.4, crop_type="Mixed vegetables", planting_date=date(2025, 4, 12), is_feed_crop=False),
    ]
    db.add_all(plots)
    db.flush()
    feed = [
        FeedBatch(farm_id=FARM_ID, plot_id=plots[0].id, name="Napier silage batch A", ingredients=["Napier grass", "Maize stover"], quantity_kg=820, batch_date=date.today()-timedelta(days=28), storage_conditions="Covered silage pit", aflatoxin_status="not_tested"),
        FeedBatch(farm_id=FARM_ID, name="Dairy meal", ingredients=["Maize bran", "Sunflower cake"], quantity_kg=340, batch_date=date.today()-timedelta(days=12), storage_conditions="Raised dry store", aflatoxin_status="pending_test"),
    ]
    db.add_all(feed)
    db.flush()
    db.add(FeedAllocation(farm_id=FARM_ID, feed_batch_id=feed[0].id, animal_id=animals[0].id, allocated_kg=18, allocated_on=date.today()-timedelta(days=1)))
    db.add_all([
        AnimalHealthEvent(farm_id=FARM_ID, animal_id=animals[0].id, created_by=VET_ID, event_type="clinical_observation", occurred_on=date.today()-timedelta(days=4), summary="Reduced appetite reported; observation follow-up scheduled.", observations={"appetite": "reduced", "temperature": "not recorded"}, follow_up_on=date.today()+timedelta(days=2), status="open", verified=True, verified_by=VET_ID),
        AnimalHealthEvent(farm_id=FARM_ID, animal_id=animals[1].id, created_by=VET_ID, event_type="vaccination", occurred_on=date.today()-timedelta(days=35), summary="Vaccination record entered; product details in farm paper log.", observations={"record_source": "farm paper log"}, follow_up_on=date.today()+timedelta(days=5), status="open", verified=True, verified_by=VET_ID),
    ])
    db.add_all([
        ProductionRecord(farm_id=FARM_ID, animal_id=animals[i % 3].id, product_type="milk", quantity=[22.4, 19.8, 24.1, 21.6, 18.9, 23.2, 20.7][i], unit="L", recorded_on=date.today()-timedelta(days=6-i))
        for i in range(7)
    ])
    manure = ManureRecord(farm_id=FARM_ID, collected_on=date.today()-timedelta(days=8), quantity_kg=165, source_notes="Collected from dairy shed")
    db.add(manure)
    db.flush()
    compost = CompostBatch(farm_id=FARM_ID, name="Compost windrow 06", manure_record_id=manure.id, created_on=date.today()-timedelta(days=7), quantity_kg=220, status="curing")
    db.add(compost)
    db.flush()
    db.add(CompostApplication(farm_id=FARM_ID, compost_batch_id=compost.id, plot_id=plots[1].id, applied_on=date.today()-timedelta(days=2), quantity_kg=45))
    production = db.query(ProductionRecord).filter(ProductionRecord.product_type == "milk").order_by(ProductionRecord.recorded_on.desc()).first()
    buyer = Buyer(name="Githunguri Demo Dairy Cooperative")
    org = Organization(name="Githunguri Demo Dairy Cooperative", kind="cooperative")
    db.add_all([buyer, org])
    db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=COOP_ID, role="cooperative_admin"))
    lot = ProductLot(farm_id=FARM_ID, production_record_id=production.id, lot_code="TV-KBU-0042-ML-001", product_type="milk", quantity=production.quantity, unit="L")
    db.add(lot)
    db.flush()
    db.add_all([
        Delivery(farm_id=FARM_ID, product_lot_id=lot.id, buyer_id=buyer.id, delivery_date=date.today(), quantity=production.quantity, unit="L", status="accepted", reference="DEMO-DEL-014"),
        Consent(farm_id=FARM_ID, granted_by=FARMER_ID, grantee_org_id=org.id, grantee_email=coop.email, scope="delivery_summary", status="active"),
    ])
    db.commit()
