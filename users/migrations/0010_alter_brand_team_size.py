from django.db import migrations, models


def migrate_team_size_forward(apps, schema_editor):
    Brand = apps.get_model("users", "Brand")
    mapping = {
        "just_me": "1",
        "small_team": "2-5",
        "medium_team": "6-20",
        "large_team": "21-50",
    }
    for old_val, new_val in mapping.items():
        Brand.objects.filter(team_size=old_val).update(team_size=new_val)


def migrate_team_size_backward(apps, schema_editor):
    Brand = apps.get_model("users", "Brand")
    reverse_mapping = {
        "1": "just_me",
        "2-5": "small_team",
        "6-20": "medium_team",
        "21-50": "large_team",
    }
    for new_val, old_val in reverse_mapping.items():
        Brand.objects.filter(team_size=new_val).update(team_size=old_val)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_user_profile_picture_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="brand",
            name="team_size",
            field=models.CharField(
                blank=True,
                choices=[
                    ("1", "1"),
                    ("2-5", "2-5"),
                    ("6-20", "6-20"),
                    ("21-50", "21-50"),
                    ("51+", "51+"),
                ],
                max_length=100,
                null=True,
            ),
        ),
        migrations.RunPython(migrate_team_size_forward, migrate_team_size_backward),
    ]
