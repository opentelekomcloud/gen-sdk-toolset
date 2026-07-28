:original_name: cce_02_0246.html

.. _cce_02_0246:

Deleting a Node
===============

Function
--------

This API is used to delete a specified node.

URI
---

DELETE /api/v3/projects/{project_id}/clusters/{cluster_id}/nodes/{node_id}

.. table:: **Table 1** Description

   ==========  =========  ============
   Parameter   Mandatory  Description
   ==========  =========  ============
   project_id  Yes        Project ID.
   node_id     Yes        Node ID.
   ==========  =========  ============

Request
-------

**Request parameters**:

.. table:: **Table 2** Parameters in the request header

   ============  =========  ==================
   Parameter     Mandatory  Description
   ============  =========  ==================
   Content-Type  Yes        Message body type.
   ============  =========  ==================

**Example request**:

N/A

Response
--------

**Response parameters**:

.. table:: **Table 3** Response parameters

   =========  ======  ==========
   Parameter  Type    Description
   =========  ======  ==========
   kind       String  API type.
   =========  ======  ==========

**Example response**:

.. code-block::

   {
       "kind": "Node",
       "apiVersion": "v3"
   }
