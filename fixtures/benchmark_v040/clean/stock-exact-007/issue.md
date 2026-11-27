# Issue: stock-exact-007

The inventory gateway rejects orders that request exactly the available stock. For 5 units available, requesting 5 should be allowed and requesting 6 rejected. Zero-unit requests should remain allowed.
