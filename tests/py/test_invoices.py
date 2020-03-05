import json

from liberapay.testing import EUR, Harness


class TestInvoices(Harness):

    def test_attaching_a_document_to_an_invoice(self):
        alice = self.make_participant('alice', allow_invoices=True)
        org = self.make_participant('org', kind='organization', allow_invoices=True)
        invoice_id = self.make_invoice(alice, org, EUR('40.02'), 'pre')
        data = {
            "conditions": [
                {"acl": "private"},
                {"bucket": "tests.liberapay.org"},
                {"Content-Type": "application/pdf"},
                {"success_action_status": "200"},
                {"x-amz-algorithm": "AWS4-HMAC-SHA256"},
                {"key": "invoice_docs/%i/Invoice_121150818.pdf" % invoice_id},
                {"x-amz-credential": "AKIAJRT6BUQHIPYENYWQ/20200225/eu-west-1/s3/aws4_request"},
                {"x-amz-date": "20200225T101507Z"},
                {"x-amz-meta-qqfilename": "Invoice_121150818.pdf"},
                ["content-length-range", "0", "5000000"]
            ],
            "expiration": "2020-02-25T10:20:07.776Z"
        }
        r = self.client.POST(
            '/org/invoices/add-file?step=sign',
            body=json.dumps(data).encode('ascii'),
            content_type=b'application/json',
            HTTP_X_INVOICE_ID=str(invoice_id),
            auth_as=alice,
        )
        assert r.code == 200, r.text
        result = json.loads(r.body)
        assert result['policy']
        assert result['signature']

        r = self.client.POST(
            '/org/invoices/add-file?step=success',
            {"name": "Invoice_121150818.pdf"},
            HTTP_X_INVOICE_ID=str(invoice_id),
            auth_as=alice,
        )
        assert r.code == 200, r.text
        assert r.body == b'{}'
