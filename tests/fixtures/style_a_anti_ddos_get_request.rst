Querying Anti-DDoS Tasks
========================

URI
---

-  URI format

   GET /v1/{project_id}/query_task_status

-  Parameter description

   ========== ========= ====== ===========
   Parameter  Mandatory Type   Description
   ========== ========= ====== ===========
   project_id Yes       String User ID
   ========== ========= ====== ===========

Request
-------

.. table:: **Table 1** Parameter description

   +-----------+-----------+--------+------------------------------------------------+
   | Parameter | Mandatory | Type   | Description                                    |
   +===========+===========+========+================================================+
   | task_id   | Yes       | String | Task ID (nonnegative integer) character string |
   +-----------+-----------+--------+------------------------------------------------+

Response
--------

None
