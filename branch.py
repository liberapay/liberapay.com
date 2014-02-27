import heapq
import psycopg2
from gittip import wireup

def main():
    db = wireup.db()
    with db.get_cursor() as c:

        claimed = c.all("""
            SELECT claimed_time as ts, id, 'claim' as action
            FROM participants
            WHERE claimed_time IS NOT NULL
            ORDER BY claimed_time
        """)
        usernames = c.all("""
            SELECT claimed_time + interval '0.01 s' as ts, id, 'set' as action, username
            FROM participants
            WHERE claimed_time IS NOT NULL
            ORDER BY claimed_time
        """)
        api_keys = c.all("""
            SELECT a.mtime as ts, p.id as id, 'set' as action, a.api_key
            FROM api_keys a
            JOIN participants p
            ON a.participant = p.username
            ORDER BY ts
        """)
        goals = c.all("""
            SELECT g.mtime as ts, p.id as id, 'set' as action, g.goal::text
            FROM goals g
            JOIN participants p
            ON g.participant = p.username
            ORDER BY ts
        """)

        for event in heapq.merge(claimed, usernames, api_keys, goals):
            payload = dict(action=event.action, id=event.id)
            if event.action == 'set':
                payload['values'] = { event._fields[-1]: event[-1] }
            c.run("""
                INSERT INTO events (ts, type, payload)
                VALUES (%s, %s, %s)
            """, (event.ts, 'participant', psycopg2.extras.Json(payload)))


if __name__ == "__main__":
    main()
