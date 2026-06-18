:original_name: elb_qy_0001.html

.. _elb_qy_0001:

Querying Backend Server Groups
==============================

Function
--------

This API is used to query all backend server groups. List endpoints split
their parameters: ``project_id`` is part of the path, while ``marker`` /
``limit`` / ``page_reverse`` are pagination query parameters.

URI
---

GET https://{Endpoint}/v3/{project_id}/elb/pools

.. table:: **Table 1** Path Parameters

   ============ ========= ====== ===========================
   Parameter    Mandatory Type   Description
   ============ ========= ====== ===========================
   project_id   Yes       String Project ID.
   ============ ========= ====== ===========================

.. table:: **Table 2** Query Parameters

   ============ ========= ======= ===========================
   Parameter    Mandatory Type    Description
   ============ ========= ======= ===========================
   marker       No        String  Pagination marker.
   limit        No        Integer Records returned per page.
   page_reverse No        Boolean Whether to page in reverse.
   ============ ========= ======= ===========================
