1. A service stores user names in users.display_name. A proposed release introduces users.full_name, changes all application reads and writes to the new column, and drops display_name in the same deployment. The service uses rolling deployment, so old and new application instances run concurrently. The release must also support rollback. Explain why this release can fail and propose a safe sequence of database and application changes.

```
Database would fail because old instances still read and write display_name, while new instances expect full_name. Rollback becomes difficult since the old application version no longer has access to its expected column.

Propesed change: 
1. Add full_name as a nullable column. 
2. Deploy an application version that write to both full_name and display_name columns, while still read from display_name. 
3. Backfill data, copy existing values from display_name into full_name. 
4. Deploy a new vesion that reads from full_name but still writes to both columns. Make sure it's compatible with old instances. 
5. After all old instances are gone and rollback is no longer needed, stop writing to display_name and drop it in a separate migration.
```



2. Certificate details are cached for 60 seconds. Request A misses the cache and reads ACTIVE
from the database. Before A writes to the cache, request B revokes the certificate, commits
the database transaction, and deletes the cache entry. A then writes its stale ACTIVE value
into the cache. A colleague proposes reducing the cache TTL to five seconds. Explain why this
does not fix the problem. Redesign the read and revocation paths so that any read starting
after B returns success cannot receive the stale ACTIVE value.

```
Reducing TTL doesn't fix the race condition. A stale write can still happen within five seconds. 


We need to prevent stale writes from overwriting newer data. So my proposed changes are: 
1. Use versioned cache entries with atomic writes.
2. Read from cache first. On a miss, read the database and only populate the cache if the version is still current.
3. Update status and version in a database transaction, commit, atomically update/invalidate the cache, then return success.
```


3. Service A has 50 request workers. Every request to its /report endpoint calls Service B with a
100 ms timeout and up to three retries. Traffic to /report remains at 1,000 requests per
second. B's latency suddenly rises from 20 ms to 2 seconds, and unrelated endpoints on A
soon stop responding. Explain the chain of failure, including the effect of retries. Redesign
/report so unrelated endpoints remain available, and state what /report should return when
B is unhealthy.

```
Failure change: 
1. A has only 50 workers. 
2. The latency of B increases from 20 ms to 2 s. 
3. A's request time out after 100 ms and rety up to 3 minutes. 
4. Workers are occupied waiting for B, while retires amplify traffic. 
5. All 50 workers become exhasusted, which caused unrelated endpoints to stop responding. 

Redesign: 
1. Isolate /report endpoint with a limited worker pool. 
2. Stop calling B when it becomes unhealthy.
3. Use exponential backoff and jitter, with a strict retry limit. 
4. Enforce request deadlines and concurrency limits. 
5. For expensive reports, we can use a background job queue. 
6. When B is unhealthy, synchorous request: 503, optionally with retry-after, async request: 202 with a job ID. 
```