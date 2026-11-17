:original_name: test_0002.html

.. _test_0002:

Creating a Router
=================

Function
--------

This API creates a router.

URI
---

POST /v2/{project_id}/routers

.. table:: **Table 1** URI parameters

   ========== ========= ====== ===========
   Parameter  Mandatory Type   Description
   ========== ========= ====== ===========
   project_id Yes       String Project ID
   ========== ========= ====== ===========

Request
-------

.. table:: **Table 2** Request body parameters

   ========= ========= ================================ ===========
   Parameter Mandatory Type                             Description
   ========= ========= ================================ ===========
   router    Yes       :ref:`router <test_0002>` object Router.
   ========= ========= ================================ ===========

Response
--------

::

   .. code-block:: text

Status Codes
------------

.. table:: **Table 3** Status codes

   =========== ===========
   Status Code Description
   =========== ===========
   200         OK
   =========== ===========
