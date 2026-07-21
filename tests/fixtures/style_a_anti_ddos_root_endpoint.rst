:original_name: antiddos_02_0002.html

.. _antiddos_02_0002:

Querying All API Versions
=========================

Functions
---------

This API allows you to query all API versions.

URI
---

-  URI format

   GET /

Request
-------

**Request parameters**

None

Response Messages
-----------------

-  Parameter description

   +-------------+---------------------+----------------------+
   | Name        | Type                | Description          |
   +=============+=====================+======================+
   | versions    | List data structure | API versions         |
   +-------------+---------------------+----------------------+
   | id          | String              | Version ID           |
   +-------------+---------------------+----------------------+
   | links       | List data structure | URLs of the APIs     |
   +-------------+---------------------+----------------------+
   | min_version | String              | Minimum microversion |
   +-------------+---------------------+----------------------+
   | status      | String              | Version status       |
   +-------------+---------------------+----------------------+
   | updated     | String              | Version release time |
   +-------------+---------------------+----------------------+
   | version     | String              | Maximum microversion |
   +-------------+---------------------+----------------------+

-  Data structure description of **links**

   ========= ====== ============
   Parameter Type   Description
   ========= ====== ============
   href      String URLs of APIs
   rel       String self
   ========= ====== ============

Example
-------

-  Example request

   .. code-block:: text

      GET /

-  Example response

   .. code-block::

      {
        "versions": [
          {
            "id": "v1",
            "links": [
              {
                "href": "https://antiddos.eu-de.otc.t-systems.com/v1/",
                "rel": "self"
              }
            ],
            "min_version": "",
            "status": "CURRENT",
            "updated": "2016-10-29T00:00:00Z",
            "version": ""
          }
        ]
      }

Status Code
-----------

For details, see :ref:`Status Code <antiddos_02_0031>`.
