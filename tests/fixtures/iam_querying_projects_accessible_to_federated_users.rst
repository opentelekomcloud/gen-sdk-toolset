:original_name: en-us_topic_0057845595.html

.. _en-us_topic_0057845595:

Querying the List of Projects Accessible to Federated Users
===========================================================

Function
--------

This API is used to query the list of projects accessible to federated users. The project list is used to obtain the scoped token in federated identity authentication mode.

URI
---

GET /v3/OS-FEDERATION/projects

Request Parameters
------------------

-  Parameters in the request header

   +--------------+-----------+--------+------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter    | Mandatory | Type   | Description                                                                                                                              |
   +==============+===========+========+==========================================================================================================================================+
   | X-Auth-Token | Yes       | String | Unscoped token. For details about how to obtain a token, see :ref:`Obtaining an Unscoped Token (SP Initiated) <en-us_topic_0057845629>`. |
   +--------------+-----------+--------+------------------------------------------------------------------------------------------------------------------------------------------+

   .. note::

      The API described in :ref:`Querying the List of Projects Accessible to Users <en-us_topic_0057845558>` is recommended. This API returns the same response format as the API described in this section.

-  Example request

   .. code-block:: text

      GET /v3/OS-FEDERATION/projects

Response Parameters
-------------------

-  Parameters in the response body

   +----------------------------------------------------------+-----------+--------+------------------------+
   | Parameter                                                | Mandatory | Type   | Description            |
   +==========================================================+===========+========+========================+
   | :ref:`projects <en-us_topic_0057845595__li445322819474>` | Yes       | array  | List of projects.      |
   +----------------------------------------------------------+-----------+--------+------------------------+
   | :ref:`links <en-us_topic_0057845595__li173351844714>`    | Yes       | Object | Project resource link. |
   +----------------------------------------------------------+-----------+--------+------------------------+

-  .. _en-us_topic_0057845595__li173351844714:

   links

   ========= ====== ==============
   Parameter Type   Description
   ========= ====== ==============
   self      string Resource link.
   ========= ====== ==============

-  .. _en-us_topic_0057845595__li445322819474:

   projects

   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+
   | Parameter                                             | Type                  | Description                                                        |
   +=======================================================+=======================+====================================================================+
   | is_domain                                             | boolean               | false.                                                             |
   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+
   | description                                           | string                | Description of the project.                                        |
   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+
   | :ref:`links <en-us_topic_0057845595__li177245019486>` | LinksSelf object      | Project resource link.                                             |
   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+
   | enabled                                               | boolean               | Whether a project is available.                                    |
   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+
   | id                                                    | string                | Project ID.                                                        |
   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+
   | parent_id                                             | string                | ID of the specified project if you query a project created by you. |
   |                                                       |                       |                                                                    |
   |                                                       |                       | Domain ID if you query a specified system built-in project.        |
   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+
   | domain_id                                             | string                | Account ID of the project.                                         |
   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+
   | name                                                  | string                | Project name.                                                      |
   +-------------------------------------------------------+-----------------------+--------------------------------------------------------------------+

-  .. _en-us_topic_0057845595__li177245019486:

   projects.links

   ========= ====== ==============
   Parameter Type   Description
   ========= ====== ==============
   self      string Resource link.
   ========= ====== ==============

-  Example response

   .. code-block::

      {
        "links": {
          "self": "https://sample.domain.com/v3/OS-FEDERATION/projects",
          "previous": null,
          "next": null
        },
        "projects": [
          {
            "is_domain": false,
            "description": "",
            "links": {
              "self": "https://sample.domain.com/v3/projects/05cf683c351e43518618d9fa96a5efa9"
            },
            "enabled": true,
            "id": "05cf683c351e43518618d9fa96a5efa9",
            "parent_id": "e31ac82d778b4d128cb6fed37fd72cdb",
            "domain_id": "e31ac82d778b4d128cb6fed37fd72cdb",
            "name": "region_name"
          },
          {
            "is_domain": false,
            "description": "",
            "links": {
              "self": "https://sample.domain.com/v3/projects/32b56f108f87418e8219317beb0fff3c"
            },
            "enabled": true,
            "id": "32b56f108f87418e8219317beb0fff3c",
            "parent_id": "e31ac82d778b4d128cb6fed37fd72cdb",
            "domain_id": "e31ac82d778b4d128cb6fed37fd72cdb",
            "name": "MOS"   //Default project name of OBS
          }
        ]
      }

Status Codes
------------

+-------------+--------------------------------------------------------------------------------+
| Status Code | Description                                                                    |
+=============+================================================================================+
| 200         | The request is successful.                                                     |
+-------------+--------------------------------------------------------------------------------+
| 400         | The server failed to process the request.                                      |
+-------------+--------------------------------------------------------------------------------+
| 401         | Authentication failed.                                                         |
+-------------+--------------------------------------------------------------------------------+
| 403         | Access denied.                                                                 |
+-------------+--------------------------------------------------------------------------------+
| 405         | The method specified in the request is not allowed for the requested resource. |
+-------------+--------------------------------------------------------------------------------+
| 413         | The request entity is too large.                                               |
+-------------+--------------------------------------------------------------------------------+
| 500         | Internal server error.                                                         |
+-------------+--------------------------------------------------------------------------------+
| 503         | Service unavailable.                                                           |
+-------------+--------------------------------------------------------------------------------+
