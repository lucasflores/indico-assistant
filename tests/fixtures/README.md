# Test Fixtures

This directory contains test files used by integration tests.

## Files

- **test_quantum.pdf**: Small valid PDF with content about "quantum computing" (used for search tests)
- **test_duplicate.pdf**: Small valid PDF with same content hash as test_quantum.pdf (used for duplicate detection tests)

## Best Practices

These files are used in **integration tests** which test the full end-to-end flow:
- File upload → Text extraction → Chunking → Embedding → Vector storage → Search

For **unit tests**, we use mocks instead of real files to test logic in isolation.

## File Sizes

All fixtures are kept minimal (<1KB) for fast test execution.
