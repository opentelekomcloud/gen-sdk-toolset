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

.. table:: **Table 2b** Parameters in the request body

   +-----------+-----------+--------------------------------+
   | Parameter | Mandatory | Description                    |
   +===========+===========+================================+
   | user_data | No        | Script injected at boot::      |
   |           |           |                                |
   |           |           |    #!/bin/bash                 |
   |           |           |    echo hello >> /tmp/out      |
   +-----------+-----------+--------------------------------+

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

The block below carries no example label, so nothing may consume it:

.. code-block::

   DELETE /api/v3/projects/{project_id}/clusters/{cluster_id}/nodes/{node_id}
