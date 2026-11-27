:original_name: evs_04_2012.html

.. _evs_04_2012:

Querying EVS Disks
==================

Function
--------

This API is used to query EVS disks and display the query results in a list.

.. important::

   This API has been deprecated. Use another API. For details, see :ref:`Querying EVS Disks <evs_04_2068>`.

URI
---

-  URI format

   GET /v2/{project_id}/cloudvolumes

-  Parameter description

   ========== ========= ===============
   Parameter  Mandatory Description
   ========== ========= ===============
   project_id Yes       The project ID.
   ========== ========= ===============

-  Request filter parameters

   +-------------------+-----------------+-----------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | Parameter         | Type            | Mandatory       | Description                                                                                                                                                            |
   +===================+=================+=================+========================================================================================================================================================================+
   | marker            | String          | No              | The ID of the resource from which the pagination query starts. It is the ID of the last resource on the previous page.                                                 |
   +-------------------+-----------------+-----------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | name              | String          | No              | The disk name. The value can contain a maximum of 255 bytes.                                                                                                           |
   +-------------------+-----------------+-----------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | status            | String          | No              | The disk status. For details, see :ref:`EVS Disk Status <evs_04_0040>`.                                                                                                |
   +-------------------+-----------------+-----------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | limit             | Integer         | No              | The maximum number of query results that can be returned.                                                                                                              |
   |                   |                 |                 |                                                                                                                                                                        |
   |                   |                 |                 | The value ranges from 1 to 1000, and the default value is 1000. The returned value cannot exceed this limit.                                                           |
   +-------------------+-----------------+-----------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | availability_zone | String          | No              | The AZ information.                                                                                                                                                    |
   +-------------------+-----------------+-----------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | sort_key          | String          | No              | The keyword based on which the returned results are sorted. The value can be **id**, **status**, **size**, or **created_at**, and the default value is **created_at**. |
   +-------------------+-----------------+-----------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+
   | sort_dir          | String          | No              | The result sorting order. The default value is **desc**.                                                                                                               |
   |                   |                 |                 |                                                                                                                                                                        |
   |                   |                 |                 | -  **desc**: the descending order                                                                                                                                      |
   |                   |                 |                 | -  **asc**: the ascending order                                                                                                                                        |
   +-------------------+-----------------+-----------------+------------------------------------------------------------------------------------------------------------------------------------------------------------------------+

Request
-------

The following example shows how to query the disks in the **available** state.

-  Example request

   .. code-block:: text

      GET https://{endpoint}/v2/{project_id}/cloudvolumes?status=available

Response
--------

-  Response parameters

   +-----------+------------------+---------------------------------------------------------------------------------------------------------------------------------+
   | Parameter | Type             | Description                                                                                                                     |
   +===========+==================+=================================================================================================================================+
   | volumes   | Array of objects | The list of queried disks. For details, see :ref:`Parameters in the volumes field <evs_04_2012__li53362106201054>`.             |
   +-----------+------------------+---------------------------------------------------------------------------------------------------------------------------------+
   | error     | Object           | The error message returned if an error occurs. For details, see :ref:`Parameters in the error field <evs_04_2012__li24688256>`. |
   +-----------+------------------+---------------------------------------------------------------------------------------------------------------------------------+

-  .. _evs_04_2012__li53362106201054:

   Parameters in the **volumes** field

   +-----------+------------------+-----------------------------------------------------------------------------------------------------+
   | Parameter | Type             | Description                                                                                         |
   +===========+==================+=====================================================================================================+
   | id        | String           | The disk ID.                                                                                        |
   +-----------+------------------+-----------------------------------------------------------------------------------------------------+
   | links     | Array of objects | The disk URI. For details, see :ref:`Parameters in the links field <evs_04_2012__li1284243594910>`. |
   +-----------+------------------+-----------------------------------------------------------------------------------------------------+
   | name      | String           | The disk name. The value can contain a maximum of 255 bytes.                                        |
   +-----------+------------------+-----------------------------------------------------------------------------------------------------+

-  .. _evs_04_2012__li1284243594910:

   Parameters in the **links** field

   ========= ====== ================================
   Parameter Type   Description
   ========= ====== ================================
   href      String The corresponding shortcut link.
   rel       String The shortcut link marker name.
   ========= ====== ================================

-  .. _evs_04_2012__li24688256:

   Parameters in the **error** field

   +-----------------------+-----------------------+-------------------------------------------------------------------------+
   | Parameter             | Type                  | Description                                                             |
   +=======================+=======================+=========================================================================+
   | message               | String                | The error message returned if an error occurs.                          |
   +-----------------------+-----------------------+-------------------------------------------------------------------------+
   | code                  | String                | The error code returned if an error occurs.                             |
   |                       |                       |                                                                         |
   |                       |                       | For details about the error code, see :ref:`Error Codes <evs_04_0038>`. |
   +-----------------------+-----------------------+-------------------------------------------------------------------------+

-  Example response

   .. code-block::

      {
          "volumes": [
              {
                  "id": "e6cf4401-15f6-44bd-ae2b-cff4dc9523e6",
                  "links": [
                      {
                          "href": "https://volume.az0.dc1.domainname.com/v2/cd631140887d4b6e9c786b67a6dd4c02/volumes/e6cf4401-15f6-44bd-ae2b-cff4dc9523e6",
                          "rel": "self"
                      },
                      {
                          "href": "https://volume.az0.dc1.domainname.com/cd631140887d4b6e9c786b67a6dd4c02/volumes/e6cf4401-15f6-44bd-ae2b-cff4dc9523e6",
                          "rel": "bookmark"
                      }
                  ],
                  "name": "hallo5"
              },
              {
                  "id": "4c5e8203-f70e-4717-90cd-4a8f636888d1",
                  "links": [
                      {
                          "href": "https://volume.az0.dc1.domainname.com/v2/cd631140887d4b6e9c786b67a6dd4c02/volumes/4c5e8203-f70e-4717-90cd-4a8f636888d1",
                          "rel": "self"
                      },
                      {
                          "href": "https://volume.az0.dc1.domainname.com/cd631140887d4b6e9c786b67a6dd4c02/volumes/4c5e8203-f70e-4717-90cd-4a8f636888d1",
                          "rel": "bookmark"
                      }
                  ],
                  "name": "hallo4"
              }
          ]
      }

   or

   .. code-block::

      {
          "error": {
              "message": "XXXX",
              "code": "XXX"
          }
      }

Status Codes
------------

-  Normal

   200

Error Codes
-----------

For details, see :ref:`Error Codes <evs_04_0038>`.
