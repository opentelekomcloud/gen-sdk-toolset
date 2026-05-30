:original_name: cce_02_0245.html

.. _cce_02_0245:

Updating a Specified Node
=========================

Function
--------

This API is used to update information about a specified node.

URI
---

PUT /api/v3/projects/{project_id}/clusters/{cluster_id}/nodes/{node_id}

:ref:`Table 1 <cce_02_0245__table2027961241820>` describes the parameters of the API.

.. _cce_02_0245__table2027961241820:

.. table:: **Table 1** Parameter description

   +------------+-----------+-------------------------------------------------------------------------------------------------------------------------------+
   | Parameter  | Mandatory | Description                                                                                                                   |
   +============+===========+===============================================================================================================================+
   | project_id | Yes       | Project ID. For details about how to obtain the project ID, see :ref:`How to Obtain Parameters in the API URI <cce_02_0271>`. |
   +------------+-----------+-------------------------------------------------------------------------------------------------------------------------------+
   | cluster_id | Yes       | Cluster ID. For details about how to obtain the cluster ID, see :ref:`How to Obtain Parameters in the API URI <cce_02_0271>`. |
   +------------+-----------+-------------------------------------------------------------------------------------------------------------------------------+
   | node_id    | Yes       | Cluster ID. For details about how to obtain the cluster ID, see :ref:`How to Obtain Parameters in the API URI <cce_02_0271>`. |
   +------------+-----------+-------------------------------------------------------------------------------------------------------------------------------+

Request
-------

**Request parameters**:

:ref:`Table 2 <cce_02_0245__table34821245101211>` and :ref:`Table 3 <cce_02_0245__table185578532300>` describe the request parameters.

.. _cce_02_0245__table34821245101211:

.. table:: **Table 2** Parameters in the request header

   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter             | Mandatory             | Description                                                                                                                                                                                                                                                                   |
   +=======================+=======================+===============================================================================================================================================================================================================================================================================+
   | Content-Type          | Yes                   | Message body type (format). Possible values:                                                                                                                                                                                                                                  |
   |                       |                       |                                                                                                                                                                                                                                                                               |
   |                       |                       | -  application/json;charset=utf-8                                                                                                                                                                                                                                             |
   |                       |                       | -  application/json                                                                                                                                                                                                                                                           |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | X-Auth-Token          | Yes                   | Requests for calling an API can be authenticated using either a token or AK/SK. If token-based authentication is used, this parameter is mandatory and must be set to a user token. For details on how to obtain a user token, see :ref:`API Usage Guidelines <cce_02_0004>`. |
   +-----------------------+-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

.. _cce_02_0245__table185578532300:

.. table:: **Table 3** Parameters in the request body

   +-----------+-----------+---------------------------------------------------------+-------------------------------------------------------+
   | Parameter | Mandatory | Type                                                    | Description                                           |
   +===========+===========+=========================================================+=======================================================+
   | metadata  | No        | :ref:`metadata <cce_02_0245__table915314146321>` object | Node's metadata, which is a collection of attributes. |
   +-----------+-----------+---------------------------------------------------------+-------------------------------------------------------+

.. _cce_02_0245__table915314146321:

.. table:: **Table 4** Data structure of the **metadata** field

   +-----------+-----------+--------+-------------------------------------------------------------------------------------------+
   | Parameter | Mandatory | Type   | Description                                                                               |
   +===========+===========+========+===========================================================================================+
   | name      | Yes       | String | Node name. After the node name is changed, the ECS name (VM name) is changed accordingly. |
   +-----------+-----------+--------+-------------------------------------------------------------------------------------------+

**Example request**:

.. code-block::

   {
       "metadata": {
           "name": "new-hostname"
       }
   }

Response
--------

**Response parameters**:

For the description of the response parameters, see :ref:`Table 4 <cce_02_0243__en-us_topic_0079616779_en-us_topic_0079614912_ref458774242>`.

**Example response**:

.. code-block::

   {
     "kind": "Node",
     "apiVersion": "v3",
     "metadata": {
       "name": "new-hostname",
       "uid": "4d1ecb2c-229a-11e8-9c75-0255ac100ceb",
       "creationTimestamp": " 2020-02-20T21:11:09Z",
       "updateTimestamp": "2020-02-20T21:11:09Z",
       "annotations": {
         "kubernetes.io/node-pool.id": "eu-de-01#s1.medium#EulerOS 2.5"
       }
     },
     "spec": {
       "flavor": "s1.medium",
       "az": "eu-de-01",
       "os": "EulerOS 2.5",
       "login": {
         "sshKey": "KeyPair-demo",
       },
       "rootVolume": {
         "volumeType": "SAS",
         "diskSize": 40
       },
       "dataVolumes": [
         {
           "volumeType": "SAS",
           "diskSize": 100
         }
       ],
       "storage": {
           "storageSelectors": [
               {
                   "name": "cceUse",
                   "storageType": "evs",
                   "matchLabels": {
                       "size": "100",
                       "volumeType": "SAS",
                       "count": "1"
                   }
               }
           ],
           "storageGroups": [
               {
                   "name": "vgpaas",
                   "selectorNames": [
                       "cceUse"
                   ],
                   "cceManaged": true,
                   "virtualSpaces": [
                       {
                           "name": "runtime",
                           "size": "90%"
                       },
                       {
                           "name": "kubernetes",
                           "size": "10%"
                       }
                   ]
               }
           ]
       },
        "publicIP": {
           "eip": {
               "bandwidth": {}
           }
        },
         "nodeNicSpec": {
             "primaryNic": {
             "subnetId": "c90b3ce5-e1f1-4c87-a006-644d78846438"
            }
        },
         "billingMode": 0
       "publicIP": {
         "eip": {
         }
       }
     },
     "status": {
       "phase": "Active",
       "serverId": "456789abc-9368-46f3-8f29-d1a95622a568",
       "publicIP": "10.34.56.78",
       "privateIP": "192.168.1.23"
     }
   }

Status Code
-----------

:ref:`Table 5 <cce_02_0245__en-us_topic_0079614900_table46761928>` describes the status code of this API.

.. _cce_02_0245__en-us_topic_0079614900_table46761928:

.. table:: **Table 5** Status code

   +-------------+---------------------------------------------------------------+
   | Status Code | Description                                                   |
   +=============+===============================================================+
   | 200         | Information about the specified node is successfully updated. |
   +-------------+---------------------------------------------------------------+

For details about error status codes, see :ref:`Status Code <cce_02_0084>`.
