from django.db import migrations


def backfill_brand_members(apps, schema_editor):
    Brand = apps.get_model("users", "Brand")
    BrandMember = apps.get_model("users", "BrandMember")
    for brand in Brand.objects.select_related("user").all():
        if brand.user_id:
            BrandMember.objects.get_or_create(
                brand=brand,
                user=brand.user,
                defaults={"role": "owner"},
            )


def rollback_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_brandinvitation_brandmember"),
    ]

    operations = [
        migrations.RunPython(backfill_brand_members, reverse_code=rollback_backfill),
    ]
