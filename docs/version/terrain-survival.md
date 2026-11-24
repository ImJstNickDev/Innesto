# Use the terrain examples in Survival

Install Copperfield and Reedbed on both peers, then join a disposable dedicated world in Survival. The [terrain setup guide](terrain-materials.md#install-both-examples) covers the independent builds, profiles and multiplayer launch.

## Collect and place the materials

The packages register materials. To get a sample patch into a fresh world, use the server's ordinary terrain editing tool to place each material within reach of the spawn. Choose the material keys shown in the operator catalogue. The sample used sand to support the rush. Suspended rush can disappear and leave pickups before the player strikes it.

1. Use the normal break action on the ochre rock and on supported rush. Walk over the drops. Select each resulting stack in the hotbar to see its held appearance. Press **I** while looking at the material to open its knowledge card.
2. Place one voxel from each stack on suitable ground, away from remaining pickups. Check the stack count before and after each placement. Both examples produced distinct saved terrain at the selected positions.
3. Retain at least 16 ochre voxels for the crafting test. Use the ordinary wood recipes to make a stick.

## Craft a stone chisel

Press **E** to open the player inventory. Put **16 ochre voxels in the top-left crafting cell and one stick directly below them**. Leave the other cells empty. Take the stone chisel from the output and put it in an empty hotbar slot. The game also announces its discovery in the wiki. For a comparison, try the same pattern with 16 rush voxels before using the ochre. The rush pattern leaves the result empty. The game also documents which ingredients accept an entire family. [Openworld crafting guide](https://www.play-openworld.com/en-gb/wiki/crafting/crafting-basics/)

Count individual voxels when comparing stacks. In a connected Survival session, the dedicated world's saved inventory changed as follows:

| Inventory | Ochre voxels | Sticks | Stone chisels |
| --- | ---: | ---: | ---: |
| Before crafting | 34 | 4 | 0 |
| After taking the result | 18 | 3 | 1 |
| After restarting and rejoining | 18 | 3 | 1 |

## Check persistence

Leave and rejoin the same server, then stop both processes normally. Relaunch Innesto with the same data directory and packages and join again. Check the material stacks, the crafted tool's hotbar slot and the two placed voxels. A separate fresh dedicated world with the same player gave an empty starting inventory.

The dedicated world saved and restored these quantities. Its operator dashboard describes inventory as reported by the client. Independent confirmation that the server validates the ingredient debit for each craft is still [tracked in issue #36](https://github.com/ImJstNickDev/Innesto/issues/36). Registering a new recipe is a separate [crafting API task](https://github.com/ImJstNickDev/Innesto/issues/5).
