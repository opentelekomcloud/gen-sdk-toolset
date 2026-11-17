:original_name: test_0001.html

.. _test_0001:

Updating a Flavor
=================

Function
--------

This API updates a flavor.

URI
---

PUT /v2/{project_id}/flavors/{flavor_id}

.. table:: **Table 1** URI parameters

   ========== ========= ====== ===========
   Parameter  Mandatory Type   Description
   ========== ========= ====== ===========
   project_id Yes       String Project ID
   flavors_id Yes       String Flavor ID
   ========== ========= ====== ===========

Request
-------

.. table:: **Table 2** Request header parameters

   ============ ========= =========================== ===========
   Parameter    Mandatory Type                        Description
   ============ ========= =========================== ===========
   X-Auth-Token Yes       User token from IAM service User token.
   ============ ========= =========================== ===========

.. table:: **Table 3** Request body parameters

   ========= ========= ========= ===================
   Parameter Mandatory Type      Description
   ========= ========= ========= ===================
   spec      Yes       Table 4   Flavor spec.
   count     No        Interger  Number of flavors.
   policy    No        REFERENCE Policy.
   ========= ========= ========= ===================

.. _test_0001__table_spec:

.. table:: **Table 4** spec

   ========= ========= ====== ===========
   Parameter Mandatory Type   Description
   ========= ========= ====== ===========
   name      Yes       String Name.
   ========= ========= ====== ===========

Example Request
---------------

.. code-block::

   {
       "spec": {"name": "small"},
       "count": 1,
   }

Status Codes
------------

.. table:: **Table 5** Status codes

   =========== ===========
   Status Code Description
   =========== ===========
   200         OK
   =========== ===========
