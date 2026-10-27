"""Seed initial contacts for the five L2 domains."""

import sqlalchemy as sa
from alembic import op

revision = "0009_seed_l2_contacts"
down_revision = "0008_l2_roster_tier"
branch_labels = None
depends_on = None


CONTACTS = [
    ("ran", "Primary L2", "Dawit Tadele", "+251 703298782", "dawit.tadele@safaricom.et"),
    ("ran", "Secondary L2", "Yalfal Tadesse", "+251 717550002", "yalfal.tadesse@safaricom.et"),
    ("power", "Primary L2", "Bisrat Awaye", "+251 711606001", "bisrat.awaye@safaricom.et"),
    ("power", "Secondary L2", "Erkeselam Leulseged", "+251 799004248", "erkeselam.leulseged@safaricom.et"),
    ("tx", "IP Layer", "Tesfamariam Nigusse", "+251 703516467", "tesfamariam.nigusse@safaricom.et"),
    ("tx", "DWDM", "Aschalew Tigabu", "+251 704662305", "aschalew.tigabu@safaricom.et"),
    ("tx", "Microwave", "Amanuel Taye", "+251 713551203", "amanuel.taye@safaricom.et"),
    ("ps_core_sdm", "Primary L2", "Dereje Gemechu", "+251 799100150", "dereje.gemechu@safaricom.et"),
    ("ps_core_sdm", "Secondary L2", "Rufael Tilahun", "+251 703768879", "rufael.tilahun@safaricom.et"),
    ("cs_core_volte", "Primary L2", "Alebachew Fanta", "+251 710227550", "alebachew.fanta@safaricom.et"),
    ("cs_core_volte", "Secondary L2", "Hiruteselassie M.", "+251 799101950", "hiruteselassie.edris@safaricom.et"),
]


def upgrade() -> None:
    connection = op.get_bind()
    insert_contact = sa.text("""
        INSERT INTO l2_roster (department, week, tier, engineer_name, phone, email, updated_at)
        SELECT :department, NULL::integer, :tier, :engineer_name, :phone, :email, CURRENT_TIMESTAMP
        WHERE NOT EXISTS (
            SELECT 1 FROM l2_roster WHERE lower(email) = lower(CAST(:email AS varchar(254)))
        )
    """)
    for department, tier, engineer_name, phone, email in CONTACTS:
        connection.execute(insert_contact, {
            "department": department,
            "tier": tier,
            "engineer_name": engineer_name,
            "phone": phone,
            "email": email,
        })


def downgrade() -> None:
    # Keep these shared contact records when rolling back schema changes.
    pass
