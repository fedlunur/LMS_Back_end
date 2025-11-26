from django.db import migrations


def drop_bad_unique_index_on_checkpoint_quiz(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor
    cursor = connection.cursor()
    table = 'courses_videocheckpointresponse'

    try:
        if vendor == 'sqlite':
            # List all indexes and drop any UNIQUE index that only covers checkpoint_quiz_id
            cursor.execute("PRAGMA index_list(%s)" % table)
            idx_rows = cursor.fetchall()  # seq, name, unique, origin, partial
            for row in idx_rows:
                # Row format differs by sqlite versions; guard by position
                try:
                    idx_name = row[1]
                    is_unique = int(row[2]) == 1
                except Exception:
                    continue
                if not is_unique:
                    continue
                # Inspect index columns
                try:
                    cursor.execute("PRAGMA index_info(%s)" % idx_name)
                    cols = [c[2] for c in cursor.fetchall()]  # seqno, cid, name
                except Exception:
                    cols = []
                # Drop UNIQUE index if it's only on checkpoint_quiz_id (not the composite unique_together)
                if cols == ['checkpoint_quiz_id']:
                    try:
                        cursor.execute('DROP INDEX IF EXISTS "%s";' % idx_name)
                    except Exception:
                        pass

        elif vendor == 'postgresql':
            # Find UNIQUE indexes that only include (checkpoint_quiz_id)
            cursor.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = %s
                  AND indexdef ILIKE '%%UNIQUE%%'
                  AND indexdef ILIKE '%%(checkpoint_quiz_id)%%'
                """,
                [table],
            )
            rows = cursor.fetchall()
            for (idx_name,) in rows:
                try:
                    cursor.execute('DROP INDEX IF EXISTS "%s";' % idx_name)
                except Exception:
                    pass

        elif vendor == 'mysql':
            # Find UNIQUE indexes that include only checkpoint_quiz_id
            cursor.execute(
                """
                SELECT INDEX_NAME
                FROM information_schema.statistics
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                  AND NON_UNIQUE = 0
                GROUP BY INDEX_NAME
                HAVING SUM(CASE WHEN COLUMN_NAME = 'checkpoint_quiz_id' THEN 1 ELSE 0 END) = COUNT(*)
                   AND COUNT(*) = 1
                """,
                [table],
            )
            rows = cursor.fetchall()
            for (idx_name,) in rows:
                try:
                    cursor.execute('ALTER TABLE `%s` DROP INDEX `%s`;' % (table, idx_name))
                except Exception:
                    pass
    finally:
        try:
            cursor.close()
        except Exception:
            pass


class Migration(migrations.Migration):
    dependencies = [
        ('courses', '0037_alter_videocheckpointquiz_options_and_more'),
    ]

    operations = [
        migrations.RunPython(drop_bad_unique_index_on_checkpoint_quiz, migrations.RunPython.noop),
    ]


